"""Teste manual do assistente (gasta cota do Gemini, por isso não vai no pytest).

Rodar: docker compose run --rm backend python -m app.teste_manual
"""
import asyncio
import time

from app.ai.responder import IAError, responder
from app.config import settings

LEITURA = {"umidade_solo": 20, "temperatura_ar": 24.1, "bomba_ligada": False}

PERGUNTAS = [
    "Como você está?",           # deve falar da sede
    "Qual é o seu pH?",          # deve dizer que não sabe
    "Quem ganhou a Copa de 2002?",  # deve recusar sem citar o solo
    "Qual a temperatura?",       # deve dizer ~24 graus, sem falar de sede
]


async def main():
    print(f"Principal: {settings.gemini_model} | Reserva: {settings.gemini_model_fallback}")
    print(f"Chave configurada: {'sim' if settings.gemini_api_key else 'NÃO'}\n")

    for p in PERGUNTAS:
        t = time.time()
        try:
            r = await responder(p, LEITURA)
            print(f"[{time.time() - t:.1f}s] ({r['modelo']}) {p}\n  -> {r['texto']}\n")
        except IAError as e:
            print(f"[{time.time() - t:.1f}s] ERRO em {p}\n  -> {e}\n")
        await asyncio.sleep(6)  # respeita o limite por minuto do plano gratuito


asyncio.run(main())