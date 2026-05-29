"""
Azure Functions entry point — wraps the FastAPI app using ASGI middleware.

The entire FastAPI application (routes, middleware, lifespan) runs inside
the Azure Functions runtime via AsgiFunctionApp.

Local dev:   func start
Production:  deployed via `func azure functionapp publish <app-name>`
"""

import azure.functions as func

from app.main import app as fastapi_app

app = func.AsgiFunctionApp(
    app=fastapi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS,
)
