FROM python:3.5
ADD . /app
WORKDIR /app
ENV PYTHONUNBUFFERED 1
CMD ["python", "actuator.py", "--inport", "9001", "--outaddr", "localhost:9000"]
