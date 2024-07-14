FROM ubuntu:latest
LABEL authors="leonidsokolov"

# I need a python, install poetry and create a virtual environment then run boz-i.py
RUN apt-get update && apt-get install -y python3 python3-pip
RUN pip3 install poetry
RUN poetry config virtualenvs.create true
RUN poetry install
RUN poetry run boz-i.py

ENTRYPOINT ["top", "-b"]