from sqlalchemy import Boolean, Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from src.database.models import Base


class MovieReaction(Base):
    __tablename__ = "movie_reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="user_movie_unique"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    movie_id = Column(
        Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False
    )
    is_like = Column(Boolean, nullable=False)

    movie = relationship("MovieModel", back_populates="reactions")
