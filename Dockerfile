FROM python:3-slim
LABEL org.opencontainers.image.authors="j@jc0b.computer"

COPY requirements.txt /krampus/

RUN pip3 install --no-cache-dir -U -r /krampus/requirements.txt

COPY . /krampus

WORKDIR /krampus
CMD ["python3", "krampus.py"]