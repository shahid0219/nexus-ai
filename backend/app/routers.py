"""Wire every module router into the FastAPI app."""
from fastapi import FastAPI

from .modules import accounts, automation, command_centre, content, github, instagram
from .modules import linkedin, monetisation, youtube


def register(app: FastAPI) -> None:
    for mod in (command_centre, instagram, youtube, linkedin, content,
                monetisation, automation, accounts, github):
        app.include_router(mod.router)
