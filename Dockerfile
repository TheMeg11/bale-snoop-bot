FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# نصب وابستگی‌ها به صورت لایه جدا برای cache شدن بیلد
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کد ربات
COPY main.py tasks.py texts.py config.py ./

# دیتابیس روی Volume متصل به /data ذخیره می‌شود (DB_PATH=/data/bot_data.db)
RUN mkdir -p /data
VOLUME ["/data"]

# وب‌سرور health (فقط برای healthcheck ریلوی — polling نیازی به پورت ندارد)
EXPOSE 8080

CMD ["python", "main.py"]
