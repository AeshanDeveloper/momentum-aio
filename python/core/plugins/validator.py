from typing import Dict, Any

class PluginValidator:
    """
    Validates plugin manifests and structural compliance.
    """
    REQUIRED_FIELDS = ["name", "version", "main"]

    @classmethod
    def validate(cls, manifest: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(manifest, dict):
            return {"valid": False, "error": "Manifest must be a JSON/dict object"}

        for field in cls.REQUIRED_FIELDS:
            if not manifest.get(field):
                return {"valid": False, "error": f"Missing required manifest field: {field}"}

        return {"valid": True, "is_verified": True}
