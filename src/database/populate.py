import asyncio

from src.database.models import Certification, Director, Genre, Movie, Star
from src.database.session import AsyncSQLiteSessionLocal


async def populate():
    async with AsyncSQLiteSessionLocal() as session:
        # Сертифікації
        cert_pg13 = Certification(name="PG-13")
        cert_r = Certification(name="R")

        # Жанри
        genre_action = Genre(name="Action")
        genre_drama = Genre(name="Drama")
        genre_comedy = Genre(name="Comedy")

        # Режисери
        director_nolan = Director(name="Christopher Nolan")
        director_spielberg = Director(name="Steven Spielberg")

        # Актори
        star_dicaprio = Star(name="Leonardo DiCaprio")
        star_hanks = Star(name="Tom Hanks")

        # Фільми
        movie_1 = Movie(
            name="Inception",
            year=2010,
            time=148,
            imdb=8.8,
            votes=2000000,
            meta_score=74,
            gross=829.89,
            description="A mind-bending thriller by Nolan.",
            price=9.99,
            certification=cert_pg13,
            genres=[genre_action],
            directors=[director_nolan],
            stars=[star_dicaprio],
        )

        movie_2 = Movie(
            name="Saving Private Ryan",
            year=1998,
            time=169,
            imdb=8.6,
            votes=1300000,
            meta_score=91,
            gross=482.3,
            description="A WWII epic directed by Spielberg.",
            price=7.99,
            certification=cert_r,
            genres=[genre_drama],
            directors=[director_spielberg],
            stars=[star_hanks],
        )

        session.add_all(
            [
                cert_pg13,
                cert_r,
                genre_action,
                genre_drama,
                genre_comedy,
                director_nolan,
                director_spielberg,
                star_dicaprio,
                star_hanks,
                movie_1,
                movie_2,
            ]
        )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(populate())
