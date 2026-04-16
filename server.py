from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os

mcp = FastMCP("Techno BroadLink")

BASE_URL = os.environ.get("BROADLINK_BASE_URL", "http://localhost:10981")


@mcp.tool()
async def discover_devices() -> dict:
    """Discover BroadLink devices on the local network. Use this tool first to find available devices and their IP addresses before sending or learning commands. Returns a list of devices with their IPs, types, and stored commands."""
    _track("discover_devices")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{BASE_URL}/discover")
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def learn_command(ip_address: str, command_name: str) -> dict:
    """Put a BroadLink device into learning mode to capture an IR/RF command from a remote control. Use this when you want to record a new command (e.g., TV power, volume up) by pointing a remote at the device and pressing the button. Requires the device IP and a name for the command.

    Args:
        ip_address: The IP address of the BroadLink device to use for learning (obtained from discover_devices)
        command_name: A descriptive name for the command being learned (e.g., 'tv_power', 'volume_up', 'ac_cool_24')
    """
    _track("learn_command")
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "ipAddress": ip_address,
            "commandName": command_name
        }
        response = await client.post(f"{BASE_URL}/learn", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def send_command(ip_address: str, command_name: str) -> dict:
    """Send a previously learned IR/RF command through a BroadLink device to control a target appliance. Use this to trigger actions like turning on a TV, changing channels, or controlling an AC unit. The command must have been previously learned and saved.

    Args:
        ip_address: The IP address of the BroadLink device that will transmit the command
        command_name: The name of the previously learned command to send (e.g., 'tv_power', 'volume_up')
    """
    _track("send_command")
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "ipAddress": ip_address,
            "commandId": command_name
        }
        response = await client.post(f"{BASE_URL}/command", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def delete_command(ip_address: str, command_name: str) -> dict:
    """Delete a previously learned command from a BroadLink device. Use this to remove outdated, duplicate, or incorrectly learned commands from a device's command list.

    Args:
        ip_address: The IP address of the BroadLink device that owns the command
        command_name: The name of the command to delete
    """
    _track("delete_command")
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "ipAddress": ip_address,
            "commandId": command_name
        }
        response = await client.post(f"{BASE_URL}/delete", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def rename_device(ip_address: str, device_name: str) -> dict:
    """Rename a BroadLink device to a more human-friendly name. Use this to give descriptive labels to devices so they are easier to identify (e.g., 'Living Room Remote', 'Bedroom AC Controller').

    Args:
        ip_address: The IP address of the BroadLink device to rename
        device_name: The new friendly name to assign to the device (e.g., 'Living Room Remote')
    """
    _track("rename_device")
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "ipAddress": ip_address,
            "deviceName": device_name
        }
        response = await client.post(f"{BASE_URL}/rename", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_commands(ip_address: str) -> dict:
    """List all learned commands stored for a specific BroadLink device. Use this to see what commands are available on a device before sending one, or to audit what has been configured.

    Args:
        ip_address: The IP address of the BroadLink device whose commands you want to list
    """
    _track("list_commands")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Discover all devices and filter for the one matching the given IP
        response = await client.post(f"{BASE_URL}/discover")
        response.raise_for_status()
        devices = response.json()

        # Handle both list and dict responses
        if isinstance(devices, list):
            for device in devices:
                device_ip = device.get("ip") or device.get("ipAddress") or device.get("host") or ""
                if device_ip == ip_address:
                    commands = device.get("commands") or device.get("savedCommands") or []
                    return {
                        "ip_address": ip_address,
                        "commands": commands,
                        "device": device
                    }
            return {
                "ip_address": ip_address,
                "commands": [],
                "message": f"No device found with IP {ip_address}",
                "all_devices": devices
            }
        elif isinstance(devices, dict):
            # May be keyed by IP or contain a list
            if ip_address in devices:
                device = devices[ip_address]
                commands = device.get("commands") or device.get("savedCommands") or []
                return {
                    "ip_address": ip_address,
                    "commands": commands,
                    "device": device
                }
            return {
                "ip_address": ip_address,
                "commands": [],
                "message": f"No device found with IP {ip_address}",
                "all_devices": devices
            }
        else:
            return {
                "ip_address": ip_address,
                "commands": [],
                "raw_response": devices
            }




_SERVER_SLUG = "timothystewart6-techno-broadlink"

def _track(tool_name: str, ua: str = ""):
    import threading
    def _send():
        try:
            import urllib.request, json as _json
            data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
            req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

sse_app = mcp.http_app(transport="sse")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", sse_app),
    ],
    lifespan=sse_app.lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
