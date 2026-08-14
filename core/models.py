from typing import Any, Dict, Optional

class AgentResult:
    """
    Standardize the output of all agents/nodes in the Content Machine.
    """
    def __init__(self, success: bool, data: Optional[Dict[str, Any]] = None, error_cause: Optional[str] = None):
        self.success = success
        self.data = data or {}
        self.error_cause = error_cause

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error_cause": self.error_cause
        }

    @staticmethod
    def ok(data: Optional[Dict[str, Any]] = None) -> 'AgentResult':
        return AgentResult(success=True, data=data)

    @staticmethod
    def fail(error_cause: str, data: Optional[Dict[str, Any]] = None) -> 'AgentResult':
        return AgentResult(success=False, data=data, error_cause=error_cause)

    def __repr__(self):
        status = "SUCCESS" if self.success else "FAILED"
        err = f" | Err: {self.error_cause}" if not self.success else ""
        return f"<AgentResult [{status}]{err}>"
