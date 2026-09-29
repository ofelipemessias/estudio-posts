FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo HOST=0.0.0.0 PORTA=5100
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY motor ./motor
COPY fonts ./fonts
COPY static ./static
EXPOSE 5100
CMD ["python", "app.py"]
