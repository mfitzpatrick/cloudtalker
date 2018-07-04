FROM python:3.5
ADD . /app
WORKDIR /app
RUN pip install -r requirements.txt
ENV PYTHONUNBUFFERED 1
CMD ["python", "cloudtalker.py", "--input_port", "9000"]
