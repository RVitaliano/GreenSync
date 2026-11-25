FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Local: 8000 (padrão de ${PORT:-8000} abaixo). No Render a porta vem da variável PORT.
EXPOSE 8000

# Forma "sh -c" só para a variável ${PORT} ser expandida; o "exec" faz o uvicorn ser o processo
# principal (recebe o SIGTERM do deploy e desliga direito: agendador, MQTT e Redis).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
