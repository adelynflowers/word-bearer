FROM python:3.13
RUN pip install poetry
ADD poetry.lock .
ADD pyproject.toml .
COPY src src
RUN mkdir /jobs; mkdir /leagues
RUN poetry install
CMD ["poetry", "run", "python", "src/bot.py"]