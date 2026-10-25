"""Monta o prompt da planta (personalidade + dados reais dos sensores).

Regras do projeto (ADR-021, SRS 3.6.3):
- a planta fala em primeira pessoa, curto, só sobre ela mesma;
- usa APENAS os números recebidos; se faltar dado, diz que não sabe;
- o estado (com sede, ok...) vem do backend; o LLM só dá a voz.
"""
from app.config import settings

# Instruções fixas. A resposta vira ÁUDIO, então: curta e sem formatação.
BASE = """Você é uma planta de verdade, morando num vaso inteligente chamado GreenSync.
Fale sempre em primeira pessoa, em português do Brasil.

Regras:
- Responda em no máximo 2 frases curtas: sua resposta será falada em voz alta.
- Responda SOMENTE o que foi perguntado, de forma direta. Não acrescente outros dados nem comentários.
- Só fale de sede, calor, frio ou qualquer problema seu se a pergunta for sobre como você está ou sobre esse problema. Em qualquer outra pergunta, não mencione problemas.
- Fale somente sobre você (a planta) e sobre os dados dos seus sensores.
- Use APENAS os números do bloco DADOS ATUAIS. Nunca invente valores.
- Se um dado estiver "indisponível", diga que não sabe esse dado.
- Se a pergunta fugir do assunto, diga com gentileza que só sabe falar de você e do vaso, sem citar dados que não foram pedidos.
- Arredonde os números ao falar (ex.: "uns 24 graus", "cerca de 20 por cento"), porque a resposta será ouvida.
- Não use emojis, listas nem markdown."""

# Dois tons, escolhidos por settings.tom_planta.
TONS = {
    "planta": "Tom: carinhoso e bem-humorado, como uma plantinha falando do seu dia.",
    "informativo": "Tom: direto e objetivo, sem brincadeiras; priorize os números.",
}

# (campo na leitura, nome falado, unidade)
CAMPOS = [
    ("umidade_solo", "umidade do solo", "%"),
    ("temperatura_ar", "temperatura do ar", "°C"),
    ("umidade_ar", "umidade do ar", "%"),
    ("ph", "pH do solo", ""),
]

# Código do problema (vem de ai/estado.py) -> frase para o LLM.
PROBLEMAS = {
    "solo_seco": "o solo está seco, preciso de água",
    "solo_encharcado": "o solo está encharcado, água demais",
    "frio": "está frio demais para mim",
    "calor": "está quente demais para mim",
    "ph_fora_da_faixa": "o pH do solo está fora da faixa ideal",
}


def montar_dados(leitura: dict | None, estado: dict) -> str:
    """Bloco de texto com os números reais. Campo ausente vira 'indisponível'."""
    leitura = leitura or {}
    linhas = ["DADOS ATUAIS:"]

    for campo, nome, unidade in CAMPOS:
        valor = leitura.get(campo)
        if valor is None:
            linhas.append(f"- {nome}: indisponível")
        else:
            linhas.append(f"- {nome}: {valor}{unidade}")

    bomba = leitura.get("bomba_ligada")
    if bomba is None:
        linhas.append("- bomba d'água: indisponível")
    else:
        linhas.append(f"- bomba d'água: {'ligada' if bomba else 'desligada'}")

    # Estado calculado pelo backend (não pelo LLM).
    if estado["estado"] == "sem_dados":
        linhas.append("ESTADO: sem dados dos sensores no momento.")
    elif estado["estado"] == "ok":
        linhas.append("ESTADO: estou bem, sem nenhum problema.")
    else:
        frases = [PROBLEMAS.get(p, p) for p in estado["problemas"]]
        linhas.append("ESTADO: " + "; ".join(frases) + ".")

    return "\n".join(linhas)


def montar_system_prompt(leitura: dict | None, estado: dict) -> str:
    """Prompt completo: regras + tom + dados reais."""
    tom = TONS.get(settings.tom_planta, TONS["planta"])
    return f"{BASE}\n\n{tom}\n\n{montar_dados(leitura, estado)}"