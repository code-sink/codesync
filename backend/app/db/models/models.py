from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base

UserAccess = Table(
    "UserAccess",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("User.user_id"), primary_key=True),
    Column("repository_id", Integer, ForeignKey("Repository.repository_id"), primary_key=True),
)

class User(Base):
    __tablename__ = "User"
    user_id = Column(Integer, primary_key=True, index=True)
    
    user_github_id = Column(String, unique=True, index=True)
    user_github_token = Column(String)
    user_github_login = Column(String, nullable=True)
    user_avatar_url = Column(String, nullable=True)

    repositories = relationship("Repository", secondary=UserAccess, back_populates="users_with_access")
    edits = relationship("Edit", back_populates="user")

class Repository(Base):
    __tablename__ = "Repository"
    repository_id = Column(Integer, primary_key=True, index=True)
    
    repo_github_id = Column(String, unique=True, index=True)  # dedup key
    repo_name = Column(String)
    repo_description = Column(String, nullable=True)
    repo_html_url = Column(String, nullable=True)
    repo_language = Column(String, nullable=True)
    repo_default_branch = Column(String, nullable=True)
    repository_is_private = Column(Boolean)
    repository_updated_at = Column(DateTime)
    installation_id = Column(Integer, nullable=True)
    
    users_with_access = relationship("User", secondary=UserAccess, back_populates="repositories")
    
    branches = relationship("Branch", back_populates="repository")

class Branch(Base):
    __tablename__ = "Branch"
    __table_args__ = (
        UniqueConstraint("repository_id", "branch_name", name="uq_branch_repo_name"),
    )
    branch_id = Column(Integer, primary_key=True, index=True)
    
    branch_name = Column(String)
    branch_created_at = Column(DateTime)
    branch_updated_at = Column(DateTime)

    repository_id = Column(Integer, ForeignKey("Repository.repository_id"))
    repository = relationship("Repository", back_populates="branches")
    files = relationship("File", back_populates="branch")

class File(Base):
    __tablename__ = "File"
    __table_args__ = (
        UniqueConstraint("branch_id", "file_path", name="uq_file_branch_path"),
    )
    file_id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    file_latest_commit = Column(String, nullable=False)

    branch_id = Column(Integer, ForeignKey("Branch.branch_id"))
    branch = relationship("Branch", back_populates="files")
    edits = relationship("Edit", back_populates="file")

class Edit(Base):
    __tablename__ = "Edit"
    edit_id = Column(Integer, primary_key=True, index=True)
    edit_timestamp = Column(DateTime)

    edit_patch = Column(String)
    edit_base_commit = Column(String)
    edit_ranges = Column(String)

    user_id = Column(Integer, ForeignKey("User.user_id"))
    user = relationship("User", back_populates="edits")

    file_id = Column(Integer, ForeignKey("File.file_id"))
    file = relationship("File", back_populates="edits")
    
    