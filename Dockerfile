FROM python:3.13
ADD poetry.lock .
ADD pyproject.toml .
COPY src src
RUN mkdir /jobs; mkdir /leagues
RUN pip install poetry
RUN poetry install
CMD ["poetry", "run", "python", "src/bot.py"]