#!/usr/bin/env python3
"""
🌐 Server Commands API - HTTP API for managing bot commands
Provides RESTful endpoints for command management
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

from bot.command_manager import get_command_manager
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Bot Commands API",
    description="RESTful API for managing bot commands without BotFather",
    version="1.0.0"
)

# Pydantic models for request/response
class CommandRequest(BaseModel):
    command: str
    description: str
    category: str = "basic"
    emoji: str = "🔹"
    enabled: bool = True

class CommandUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[str] = None
    emoji: Optional[str] = None
    enabled: Optional[bool] = None

class MenuLayoutUpdate(BaseModel):
    layout: Dict[str, List[List[str]]]

# Global command manager
command_manager = get_command_manager()


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Bot Commands API",
        "version": "1.0.0",
        "endpoints": {
            "commands": "/commands",
            "categories": "/categories",
            "menu": "/menu",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "commands_loaded": len(command_manager.commands_config.get('commands', []))
    }


# Commands endpoints
@app.get("/commands")
async def list_commands(
    category: Optional[str] = Query(None, description="Filter by category"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status")
) -> JSONResponse:
    """List all commands with optional filtering."""
    try:
        commands = command_manager.commands_config.get('commands', [])

        # Apply filters
        if category:
            commands = [cmd for cmd in commands if cmd.get('category') == category]

        if enabled is not None:
            commands = [cmd for cmd in commands if cmd.get('enabled', True) == enabled]

        return JSONResponse({
            "success": True,
            "count": len(commands),
            "commands": commands
        })

    except Exception as e:
        logger.error(f"Error listing commands: {e}")
        raise HTTPException(status_code=500, detail="Failed to list commands")


@app.get("/commands/{command}")
async def get_command(command: str) -> JSONResponse:
    """Get specific command information."""
    try:
        cmd_info = command_manager.get_command_info(command)
        if cmd_info:
            return JSONResponse({
                "success": True,
                "command": cmd_info
            })
        else:
            raise HTTPException(status_code=404, detail=f"Command '{command}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting command '{command}': {e}")
        raise HTTPException(status_code=500, detail="Failed to get command")


@app.post("/commands")
async def create_command(command_req: CommandRequest) -> JSONResponse:
    """Create a new command."""
    try:
        success = command_manager.add_command(
            command_req.command,
            command_req.description,
            command_req.category,
            command_req.emoji
        )

        if success:
            return JSONResponse({
                "success": True,
                "message": f"Command '/{command_req.command}' created successfully",
                "command": command_req.dict()
            })
        else:
            raise HTTPException(status_code=400, detail="Failed to create command")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating command: {e}")
        raise HTTPException(status_code=500, detail="Failed to create command")


@app.put("/commands/{command}")
async def update_command(command: str, update: CommandUpdate) -> JSONResponse:
    """Update an existing command."""
    try:
        cmd_info = command_manager.get_command_info(command)
        if not cmd_info:
            raise HTTPException(status_code=404, detail=f"Command '{command}' not found")

        # Update fields
        if update.description is not None:
            cmd_info['description'] = update.description
        if update.category is not None:
            cmd_info['category'] = update.category
        if update.emoji is not None:
            cmd_info['emoji'] = update.emoji
        if update.enabled is not None:
            cmd_info['enabled'] = update.enabled

        # Save updated config
        commands = command_manager.commands_config.get('commands', [])
        for i, cmd in enumerate(commands):
            if cmd['command'] == command:
                commands[i] = cmd_info
                break

        command_manager.commands_config['commands'] = commands
        success = command_manager.save_commands()

        if success:
            return JSONResponse({
                "success": True,
                "message": f"Command '/{command}' updated successfully",
                "command": cmd_info
            })
        else:
            raise HTTPException(status_code=400, detail="Failed to update command")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating command '{command}': {e}")
        raise HTTPException(status_code=500, detail="Failed to update command")


@app.delete("/commands/{command}")
async def delete_command(command: str) -> JSONResponse:
    """Delete a command."""
    try:
        success = command_manager.remove_command(command)
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Command '/{command}' deleted successfully"
            })
        else:
            raise HTTPException(status_code=404, detail=f"Command '{command}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting command '{command}': {e}")
        raise HTTPException(status_code=500, detail="Failed to delete command")


@app.post("/commands/{command}/toggle")
async def toggle_command(command: str) -> JSONResponse:
    """Toggle command enabled status."""
    try:
        new_status = command_manager.toggle_command(command)
        if new_status is not None:
            status_text = "enabled" if new_status else "disabled"
            return JSONResponse({
                "success": True,
                "message": f"Command '/{command}' {status_text}",
                "enabled": new_status
            })
        else:
            raise HTTPException(status_code=404, detail=f"Command '{command}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling command '{command}': {e}")
        raise HTTPException(status_code=500, detail="Failed to toggle command")


# Categories endpoints
@app.get("/categories")
async def list_categories() -> JSONResponse:
    """List all command categories."""
    try:
        categories = command_manager.commands_config.get('categories', {})
        return JSONResponse({
            "success": True,
            "count": len(categories),
            "categories": categories
        })

    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to list categories")


# Menu layout endpoints
@app.get("/menu")
async def get_menu_layout() -> JSONResponse:
    """Get current menu layout."""
    try:
        layout = command_manager.get_menu_layout()
        return JSONResponse({
            "success": True,
            "layout": layout
        })

    except Exception as e:
        logger.error(f"Error getting menu layout: {e}")
        raise HTTPException(status_code=500, detail="Failed to get menu layout")


@app.put("/menu")
async def update_menu_layout(menu_update: MenuLayoutUpdate) -> JSONResponse:
    """Update menu layout."""
    try:
        success = command_manager.update_menu_layout(menu_update.layout)
        if success:
            return JSONResponse({
                "success": True,
                "message": "Menu layout updated successfully",
                "layout": menu_update.layout
            })
        else:
            raise HTTPException(status_code=400, detail="Failed to update menu layout")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating menu layout: {e}")
        raise HTTPException(status_code=500, detail="Failed to update menu layout")


# Configuration endpoints
@app.get("/config")
async def get_config() -> JSONResponse:
    """Get complete commands configuration."""
    try:
        return JSONResponse({
            "success": True,
            "config": command_manager.commands_config
        })

    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail="Failed to get configuration")


@app.post("/reload")
async def reload_config() -> JSONResponse:
    """Reload commands from configuration file."""
    try:
        command_manager.reload_commands()
        return JSONResponse({
            "success": True,
            "message": "Configuration reloaded successfully"
        })

    except Exception as e:
        logger.error(f"Error reloading config: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload configuration")


# Backup/Restore endpoints
@app.post("/backup")
async def create_backup() -> JSONResponse:
    """Create a backup of current configuration."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_commands_{timestamp}.json"

        success = command_manager.export_commands(backup_file)
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Backup created successfully",
                "backup_file": backup_file,
                "timestamp": timestamp
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to create backup")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail="Failed to create backup")


@app.post("/restore")
async def restore_backup(file_path: str = Body(..., embed=True)) -> JSONResponse:
    """Restore configuration from backup file."""
    try:
        success = command_manager.import_commands(file_path)
        if success:
            return JSONResponse({
                "success": True,
                "message": f"Configuration restored from {file_path}"
            })
        else:
            raise HTTPException(status_code=400, detail="Failed to restore backup")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring backup: {e}")
        raise HTTPException(status_code=500, detail="Failed to restore backup")


# Statistics endpoint
@app.get("/stats")
async def get_stats() -> JSONResponse:
    """Get command statistics."""
    try:
        commands = command_manager.commands_config.get('commands', [])
        categories = command_manager.commands_config.get('categories', {})

        enabled_count = sum(1 for cmd in commands if cmd.get('enabled', True))
        disabled_count = len(commands) - enabled_count

        # Commands by category
        category_counts = {}
        for cmd in commands:
            category = cmd.get('category', 'other')
            category_counts[category] = category_counts.get(category, 0) + 1

        return JSONResponse({
            "success": True,
            "stats": {
                "total_commands": len(commands),
                "enabled_commands": enabled_count,
                "disabled_commands": disabled_count,
                "total_categories": len(categories),
                "commands_by_category": category_counts,
                "last_updated": command_manager.commands_config.get('last_updated'),
                "version": command_manager.commands_config.get('version', 'unknown')
            }
        })

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


def run_server(host: str = "127.0.0.1", port: int = 8000):
    """Run the API server."""
    print(f"🌐 Starting Bot Commands API Server")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Documentation: http://{host}:{port}/docs")
    print(f"   Health Check: http://{host}:{port}/health")
    print()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bot Commands API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()
    run_server(args.host, args.port)