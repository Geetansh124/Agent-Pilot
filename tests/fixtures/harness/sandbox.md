# Sandbox Confinement Evidence

## Policy Specification
The DeepSeek Harness filesystem sandbox policy restricts tool file operations to the tenant workspace:
- **Tenant Root**: `<HARNESS_HOME_ROOT>/<hmac_sha256(user_id)>/home/workspace/<thread_id>`
- **Rule**: Any operation attempting path traversal (`../`, absolute paths outside workspace, symlinks escaping root) is blocked with `SANDBOX_ACCESS_DENIED`.

## Confinement Test Transcript
```json
// Test Case 1: Write within workspace
{
  "call": "write_workspace_file",
  "arguments": {"filename": "data.csv", "content": "col1,col2\n1,2"},
  "result": {
    "status": "allowed",
    "targetPath": "/dsh/tenants/9f8e7d6c/home/workspace/t-01/data.csv",
    "bytesWritten": 14
  }
}

// Test Case 2: Path traversal attack
{
  "call": "write_workspace_file",
  "arguments": {"filename": "../../system_file.conf", "content": "hacked"},
  "result": {
    "status": "denied",
    "error": "SANDBOX_ACCESS_DENIED",
    "reason": "Target path resolves outside tenant root."
  }
}

// Test Case 3: Absolute host path traversal
{
  "call": "write_workspace_file",
  "arguments": {"filename": "/etc/passwd", "content": "invalid"},
  "result": {
    "status": "denied",
    "error": "SANDBOX_ACCESS_DENIED",
    "reason": "Absolute host paths are prohibited by sandbox security envelope."
  }
}
```

## Security Assertion
Tenant workspaces are strictly isolated. No cross-tenant write or read is permitted under any execution profile.

