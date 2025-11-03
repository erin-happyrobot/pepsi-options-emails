#!/usr/bin/env python3
"""
Server startup script for the FastAPI email application.

This script creates and runs the FastAPI application with the email endpoints.
"""

import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add the package to path
# Since run_server.py is now in the repo root (pepsi-options-emails/),
# the package modules are in the same directory
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Handle relative imports by temporarily changing directory
# or by creating a proper package structure
import importlib.util

# Create a mock package structure for relative imports
class MockModule:
    def __init__(self, name):
        self.__name__ = name
        
# Set up sys.modules for relative imports
sys.modules['pepsi_options_emails'] = MockModule('pepsi_options_emails')

# Import main module with proper handling of relative imports
# Modules are in the same directory as run_server.py
main_path = os.path.join(project_root, "main.py")
main_spec = importlib.util.spec_from_file_location("pepsi_options_emails.main", main_path)
main_module = importlib.util.module_from_spec(main_spec)

# Import dependencies and register them in sys.modules for relative imports
for module_name in ['db', 'scheduler', 'email_service']:
    module_path = os.path.join(project_root, f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(f"pepsi_options_emails.{module_name}", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"pepsi_options_emails.{module_name}"] = module
    spec.loader.exec_module(module)

# Now load main module
sys.modules['pepsi_options_emails.main'] = main_module
main_spec.loader.exec_module(main_module)

router = main_module.router
lifespan = main_module.lifespan

# Create FastAPI app
app = FastAPI(
    title="Pepsi Options Email Service",
    description="Service that queries options data and sends emails via Lambda",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware (optional, useful for testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the router
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or use default
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    
    print(f"Starting server on http://{host}:{port}")
    print(f"API docs available at http://{host}:{port}/docs")
    print("\nAvailable endpoints:")
    print("  POST /send-email - Send email with options data")
    print("  POST /webhook - Legacy webhook endpoint (same as /send-email)")
    print("  POST / - Root endpoint (same as /send-email)")
    print("  POST /scheduler/start - Start email scheduler")
    print("  POST /scheduler/stop - Stop email scheduler")
    print("  GET /scheduler/status - Get scheduler status")
    print("\nPress CTRL+C to stop the server")
    
    uvicorn.run(app, host=host, port=port)

