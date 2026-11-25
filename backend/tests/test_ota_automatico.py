"""OTA automático: semver, PUT que dispara, status online que dispara, tentativas e bloqueio."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import mqtt_client
from app.config import settings
from app.ota import automatico, repositorio, servico
from app.ota import validacao as v
from app.routes import firmware as rota_fw
from tests.falso_firestore import FIRESTORE_FALSO, DbFalso
from tests.falsos import leitura_ok

URL = "https://github.com/o/r/releases/download/v{}/fw.bin"
HASH = "ab" * 32
ADMIN = {"X-Admin-Key": "admin-secreta"}


def agora():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- semver ----

@pytest.mark.parametrize("a,b,esperado", [
    ("1.0.0", "1.0.1", -1), ("1.0.1", "1.0.0", 1), ("1.0.0", "1.0.0", 0),
    ("1.9.0", "1.10.0", -1),                      # número, não texto
    ("2.0.0", "1.99.99", 1),
    ("1.0.0-rc1", "1.0.0", -1),                   # pré-lançamento vale menos que a final
    ("1.0.0", "1.0.0-rc1", 1),
    ("1.0.0-rc1", "1.0.0-rc2", -1),
    ("1.0.0-rc.2", "1.0.0-rc.10", -1),
    ("1.0.0-1", "1.0.0-a", -1),                   # número < texto
    ("1.0.0-rc", "1.0.0-rc.1", -1),               # prefixo menor < maior
    ("1.0.0-rc1", "1.0.1-rc1", -1),
])
def test_comparar_versoes(a, b, esperado):
    assert v.comparar_versoes(a, b) == esperado
    assert v.versao_maior(a, b) is (esperado > 0)


@pytest.mark.parametrize("a,b", [("lixo", "1.0.0"), ("1.0.0", "1.0"), ("", "1.0.0"), ("1.0.0", None)])
def test_comparar_versao_invalida_levanta(a, b):
    with pytest.raises(v.ErroValidacao):
        v.comparar_versoes(a, b)


def test_configuracao_padrao():
    assert settings.ota_auto is False and settings.ota_auto_tentativas == 2


# ------------------------------------------------------------- montagem ----

class Montagem:
    def __init__(self):
        self.db = DbFalso()
        self.publicados = []
        self.leituras = {}
        self.erro_publicacao = None
        self.db.store["firmware"] = {
            "wroom": {"versao": "2.0.0", "url": URL.format("2"), "sha256": HASH, "notas": None,
                      "anterior": None, "bloqueadas": [], "publicado_em": agora()},
            "s3": {"versao": "2.0.0", "url": URL.format("2s"), "sha256": HASH, "notas": None,
                   "anterior": None, "bloqueadas": [], "publicado_em": agora()},
        }
        self.db.store["devices"] = {}

    def vaso(self, device_id, status="online", fw=None, fw_s3=None, **extra):
        d = {"status": status, **extra}
        if fw is not None:
            d["fw"] = fw
        if fw_s3 is not None:
            d["fw_s3"] = fw_s3
        self.db.store["devices"][device_id] = d

    async def publicar(self, device_id, payload):
        if self.erro_publicacao:
            raise self.erro_publicacao
        self.publicados.append((device_id, payload))

    def para(self, device_id):
        return [p for d, p in self.publicados if d == device_id]

    def doc(self, device_id):
        return self.db.doc("devices", device_id)


@pytest.fixture
def m(monkeypatch):
    m = Montagem()
    monkeypatch.setattr(repositorio, "init_firebase", lambda: m.db)
    monkeypatch.setattr(repositorio, "firestore", FIRESTORE_FALSO)
    monkeypatch.setattr(servico, "publicar_comando", m.publicar)
    monkeypatch.setattr(servico, "trava", asyncio.Lock())
    monkeypatch.setattr(settings, "ota_auto", True)
    monkeypatch.setattr(settings, "ota_auto_tentativas", 2)
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")

    async def leitura(device_id):
        return m.leituras.get(device_id, leitura_ok())

    monkeypatch.setattr(automatico, "ler_leitura_segura", leitura)

    async def salvar_status(device_id, status, fw=None, fw_s3=None):     # no lugar do Firestore real
        d = m.db.store["devices"].setdefault(device_id, {})
        d["status"] = status
        if fw:
            d["fw"] = fw
        if fw_s3:
            d["fw_s3"] = fw_s3

    monkeypatch.setattr(mqtt_client, "save_status", salvar_status)
    return m


def status_msg(device_id, status="online", **extra):
    return SimpleNamespace(topic=SimpleNamespace(value=f"greensync/{device_id}/status"),
                           payload=json.dumps({"status": status, **extra}).encode())


async def chega_status(m, device_id, status="online", **extra):
    await mqtt_client.handle_message(status_msg(device_id, status, **extra))
    await automatico.aguardar_pendentes()


# ---------------------------------------------------- PUT /firmware/{alvo} ----

@pytest.fixture
def c(m):
    app = FastAPI()
    app.include_router(rota_fw.router)
    return TestClient(app)


def put(c, versao="3.0.0", alvo="wroom"):
    return c.put(f"/firmware/{alvo}", headers=ADMIN,
                 json={"versao": versao, "url": URL.format(versao), "sha256": HASH})


def test_put_dispara_so_para_vasos_online_e_com_versao_menor(m, c):
    m.vaso("v1", fw="1.0.0")                      # online e menor      -> sim
    m.vaso("v2", status="offline", fw="1.0.0")    # offline             -> não
    m.vaso("v3", fw="3.5.0")                      # maior               -> não
    m.vaso("v4", fw="3.0.0")                      # igual               -> não
    m.vaso("v5")                                  # versão desconhecida -> não
    m.vaso("v6", fw="2.0.0")                      # online e menor      -> sim
    r = put(c)
    assert r.status_code == 200
    assert sorted(d for d, _ in m.publicados) == ["v1", "v6"]
    cmd = m.para("v1")[0]
    assert (cmd["acao"], cmd["alvo"], cmd["versao"]) == ("atualizar", "wroom", "3.0.0")
    assert cmd["url"] == URL.format("3.0.0") and cmd["sha256"] == HASH
    assert m.doc("v1")["ota"]["estado"] == "solicitada"
    assert m.doc("v1")["ota_auto"] == {"wroom": {"versao": "3.0.0", "tentativas": 1, "ultimo_erro": None}}
    assert "ota" not in m.doc("v2") and "ota_auto" not in m.doc("v2")


def test_put_resposta_nao_muda_com_o_automatico(m, c, monkeypatch):
    m.vaso("v1", fw="1.0.0")
    r = put(c)
    assert r.status_code == 200
    assert set(r.json()) == {"versao", "url", "sha256", "notas", "publicado_em", "anterior", "bloqueadas"}
    assert r.json()["versao"] == "3.0.0" and r.json()["anterior"]["versao"] == "2.0.0"


def test_put_com_ota_auto_desligado_nao_faz_nada(m, c, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto", False)
    m.vaso("v1", fw="1.0.0")
    assert put(c).status_code == 200
    assert m.publicados == [] and "ota" not in m.doc("v1")


def test_put_erro_no_despacho_nao_afeta_a_resposta(m, c, monkeypatch):
    async def quebra():
        raise RuntimeError("firestore fora")

    monkeypatch.setattr(repositorio, "listar_dispositivos", quebra)
    r = put(c)
    assert r.status_code == 200 and r.json()["versao"] == "3.0.0"


def test_put_recusado_nao_despacha(m, c):
    m.vaso("v1", fw="1.0.0")
    assert put(c, versao="2.0.0").status_code == 409          # igual à atual
    assert m.publicados == []


def test_put_um_vaso_com_problema_nao_impede_os_outros(m, c):
    m.vaso("v1", fw="1.0.0")
    m.vaso("v2", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)           # recusa; o v2 segue
    put(c)
    assert [d for d, _ in m.publicados] == ["v2"]
    assert "ota_auto" not in m.doc("v1")                       # recusa não conta tentativa


def test_put_s3_compara_fw_s3(m, c):
    m.vaso("v1", fw="9.0.0", fw_s3="1.0.0")
    put(c, versao="3.0.0", alvo="s3")
    assert m.para("v1")[0]["alvo"] == "s3"


# ------------------------------------------------------- status "online" ----

@pytest.mark.anyio
async def test_status_online_com_versao_menor_dispara(m):
    m.vaso("v1", status="offline")
    await chega_status(m, "v1", fw="1.0.0")
    assert m.para("v1") == [{"acao": "atualizar", "alvo": "wroom", "id": m.doc("v1")["ota"]["id"],
                             "versao": "2.0.0", "url": URL.format("2"), "sha256": HASH}]
    assert m.doc("v1")["ota"]["tipo"] == "atualizar" and m.doc("v1")["ota_auto"]["wroom"]["tentativas"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize("fw",["2.0.0", "2.1.0", "3.0.0", "10.0.0"])
async def test_status_online_com_versao_igual_ou_maior_nao_dispara(m, fw):
    await chega_status(m, "v1", fw=fw)
    assert m.publicados == []


@pytest.mark.anyio
async def test_prerelease_e_menor_que_a_final(m):
    await chega_status(m, "v1", fw="2.0.0-rc1")
    assert len(m.publicados) == 1


@pytest.mark.anyio
async def test_status_online_sem_versao_informada_nao_dispara(m):
    await chega_status(m, "v1")
    assert m.publicados == []


@pytest.mark.anyio
async def test_status_offline_nao_dispara(m):
    await chega_status(m, "v1", status="offline", fw="1.0.0")
    assert m.publicados == []


@pytest.mark.anyio
async def test_ota_auto_desligado_nao_faz_nada(m, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto", False)
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == [] and "ota" not in m.doc("v1")


@pytest.mark.anyio
async def test_versao_bloqueada_nao_e_instalada(m):
    m.db.store["firmware"]["wroom"]["bloqueadas"] = ["2.0.0"]          # a atual também está bloqueada
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == []


@pytest.mark.anyio
async def test_os_dois_alvos_abaixo_publicam_um_de_cada_vez(m):
    await chega_status(m, "v1", fw="1.0.0", fw_s3="1.0.0")
    assert [p["alvo"] for _, p in m.publicados] == ["wroom"]            # s3: ota_em_curso


@pytest.mark.anyio
async def test_recusas_do_servico_continuam_valendo_e_nao_contam_tentativa(m):
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == [] and "ota_auto" not in m.doc("v1")
    m.leituras["v1"] = None                                             # sem_dados
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == [] and "ota_auto" not in m.doc("v1")


# ---------------------------------------------------- OTA em andamento ----

@pytest.mark.anyio
@pytest.mark.parametrize("estado", ["solicitada", "baixando", "aplicando"])
async def test_ota_em_andamento_nao_duplica(m, estado):
    m.vaso("v1", fw="1.0.0", ota={"alvo": "wroom", "id": "x", "versao": "2.0.0", "tipo": "atualizar",
                                  "estado": estado, "atualizado_em": agora()})
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == [] and m.doc("v1")["ota"]["id"] == "x"


@pytest.mark.anyio
async def test_ota_travada_antiga_permite(m):
    m.vaso("v1", fw="1.0.0", ota={"alvo": "wroom", "id": "x", "versao": "2.0.0", "tipo": "atualizar",
                                  "estado": "baixando",
                                  "atualizado_em": agora() - timedelta(seconds=settings.ota_timeout_s + 10)})
    await chega_status(m, "v1", fw="1.0.0")
    assert len(m.publicados) == 1


@pytest.mark.anyio
async def test_duas_verificacoes_ao_mesmo_tempo_publicam_uma_vez(m):
    m.vaso("v1", fw="1.0.0")
    await asyncio.gather(automatico.despachar_automatico("v1", "wroom"),
                         automatico.despachar_automatico("v1", "wroom"),
                         automatico.verificar_vaso_online("v1"))
    assert len(m.publicados) == 1


# -------------------------------------------------------- tentativas ----

@pytest.mark.anyio
async def test_limite_de_tentativas_por_versao(m):
    m.vaso("v1", fw="1.0.0")
    for _ in range(4):
        await chega_status(m, "v1", fw="1.0.0")
        m.doc("v1")["ota"]["estado"] = "falhou"        # a tentativa terminou mal; o vaso segue em 1.0.0
    assert len(m.publicados) == 2                       # OTA_AUTO_TENTATIVAS = 2
    assert m.doc("v1")["ota_auto"]["wroom"]["tentativas"] == 2


@pytest.mark.anyio
async def test_limite_configuravel(m, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto_tentativas", 1)
    m.vaso("v1", fw="1.0.0")
    for _ in range(3):
        await chega_status(m, "v1", fw="1.0.0")
        m.doc("v1")["ota"]["estado"] = "falhou"
    assert len(m.publicados) == 1


@pytest.mark.anyio
async def test_limite_zero_nunca_tenta(m, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto_tentativas", 0)
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == []


@pytest.mark.anyio
async def test_versao_nova_recomeca_a_contagem(m):
    m.vaso("v1", fw="1.0.0", ota_auto={"wroom": {"versao": "1.5.0", "tentativas": 2, "ultimo_erro": "hash"}})
    await chega_status(m, "v1", fw="1.0.0")
    assert len(m.publicados) == 1
    assert m.doc("v1")["ota_auto"] == {"wroom": {"versao": "2.0.0", "tentativas": 1, "ultimo_erro": None}}


@pytest.mark.anyio
async def test_alcancar_a_versao_zera_as_tentativas(m):
    m.vaso("v1", fw="1.0.0", ota_auto={"wroom": {"versao": "2.0.0", "tentativas": 2, "ultimo_erro": "hash"}})
    await chega_status(m, "v1", fw="2.0.0")
    assert m.publicados == []
    assert m.doc("v1")["ota_auto"] == {"wroom": {"versao": "2.0.0", "tentativas": 0, "ultimo_erro": None}}


@pytest.mark.anyio
async def test_wroom_alcancar_a_versao_nao_zera_a_contagem_do_s3(m):
    auto = {"s3": {"versao": "2.0.0", "tentativas": 1, "ultimo_erro": "hash"}}
    m.vaso("v1", fw="2.0.0", fw_s3="1.0.0", ota_auto=dict(auto),
           ota={"alvo": "s3", "id": "x", "versao": "2.0.0", "tipo": "atualizar",
                "estado": "baixando", "atualizado_em": agora()})            # s3 em andamento: nada a despachar
    await chega_status(m, "v1", fw="2.0.0")                                    # o wroom está na versão
    assert m.doc("v1")["ota_auto"] == auto and m.publicados == []


@pytest.mark.anyio
async def test_falha_na_publicacao_conta_tentativa_e_guarda_o_erro(m):
    m.erro_publicacao = ConnectionError("broker fora")
    m.vaso("v1", fw="1.0.0")
    await chega_status(m, "v1", fw="1.0.0")
    assert m.doc("v1")["ota_auto"] == {"wroom": {"versao": "2.0.0", "tentativas": 1,
                                                 "ultimo_erro": "não consegui falar com o broker"}}


@pytest.mark.anyio
async def test_falha_informada_pelo_vaso_vira_ultimo_erro(m):
    m.vaso("v1", fw="1.0.0")
    await chega_status(m, "v1", fw="1.0.0")
    ota_id = m.doc("v1")["ota"]["id"]
    msg = SimpleNamespace(topic=SimpleNamespace(value="greensync/v1/ota"), payload=json.dumps(
        {"alvo": "wroom", "id": ota_id, "estado": "falhou", "versao": "2.0.0", "erro": "hash"}).encode())
    await mqtt_client.handle_message(msg)
    assert m.doc("v1")["ota"]["estado"] == "falhou"
    wroom = m.doc("v1")["ota_auto"]["wroom"]
    assert wroom["ultimo_erro"] == "hash" and wroom["tentativas"] == 1


@pytest.mark.anyio
async def test_erro_no_firestore_nao_derruba_o_tratamento_do_status(m, monkeypatch):
    async def quebra(device_id):
        raise RuntimeError("firestore fora")

    monkeypatch.setattr(repositorio, "ler_dispositivo", quebra)
    await chega_status(m, "v1", fw="1.0.0")             # não levanta
    assert m.publicados == []


# ------------------------------------------------------ reverter bloqueia ----

def _boa(m, versao="1.0.0"):
    m.db.store["firmware"]["wroom"].update({"versao": versao, "url": URL.format(versao), "bloqueadas": []})


async def reverter(m, device_id="v1", alvo="wroom"):
    leitura = leitura_ok()
    from app.ai.estado import avaliar_estado
    return await servico.solicitar_reversao(device_id, alvo, leitura, avaliar_estado(leitura))


@pytest.mark.anyio
async def test_reverter_bloqueia_a_versao_revertida(m):
    _boa(m)
    m.vaso("v1", fw="2.0.0")
    r = await reverter(m)
    assert r["resultado"] == "solicitada"
    assert m.db.doc("firmware", "wroom")["bloqueadas"] == ["2.0.0"]
    assert m.db.doc("firmware", "wroom")["versao"] == "1.0.0"          # a atual do registro não muda


@pytest.mark.anyio
async def test_reverter_nao_duplica_na_lista(m):
    _boa(m)
    m.db.store["firmware"]["wroom"]["bloqueadas"] = ["2.0.0"]
    m.vaso("v1", fw="2.0.0")
    await reverter(m)
    assert m.db.doc("firmware", "wroom")["bloqueadas"] == ["2.0.0"]


@pytest.mark.anyio
async def test_reverter_com_versao_instalada_desconhecida_nao_bloqueia_nada(m):
    _boa(m)
    m.vaso("v1")
    assert (await reverter(m))["resultado"] == "solicitada"
    assert m.db.doc("firmware", "wroom")["bloqueadas"] == []


@pytest.mark.anyio
async def test_reverter_recusado_ou_que_falha_na_publicacao_nao_bloqueia(m):
    _boa(m)
    m.vaso("v1", fw="1.0.0")                                           # versao_igual: recusada
    assert (await reverter(m))["motivo"] == "versao_igual"
    m.vaso("v2", fw="2.0.0")
    m.erro_publicacao = ConnectionError("broker fora")
    assert (await reverter(m, "v2"))["resultado"] == "falhou"
    assert m.db.doc("firmware", "wroom")["bloqueadas"] == []


@pytest.mark.anyio
async def test_nunca_bloqueia_a_versao_atual_do_registro(m):
    assert await repositorio.bloquear_versao("wroom", "2.0.0") is False        # é a atual
    assert await repositorio.bloquear_versao("s3", "9.9.9") is True
    assert await repositorio.bloquear_versao("s3", "9.9.9") is False           # já estava
    assert await repositorio.bloquear_versao("inexistente", "1.0.0") is False


def test_versao_revertida_nao_pode_ser_registrada_de_novo(m, c):
    _boa(m)
    m.vaso("v1", fw="2.0.0")
    asyncio.run(reverter(m))
    assert put(c, versao="2.0.0").status_code == 409


@pytest.mark.anyio
async def test_depois_de_reverter_o_automatico_nao_reinstala(m):
    _boa(m)                                                            # registro: 1.0.0 (a boa)
    m.vaso("v1", fw="2.0.0")
    await reverter(m)
    m.publicados.clear()
    m.doc("v1")["ota"]["estado"] = "revertido"
    m.doc("v1")["fw"] = "1.0.0"                                        # o vaso voltou
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == []
