from fastapi import Header, HTTPException

def verify_tenant_context(x_tenant_id: str = Header(..., description="Mandatory Tenant ID Header")):
    """
    Dependency to ensure the caller (Secure Gateway) explicitly provides the tenant context.
    The Vector Service refuses to process any request missing this context.
    """
    if not x_tenant_id or x_tenant_id.strip() == "":
        raise HTTPException(status_code=400, detail="Missing Tenant Context")
    return x_tenant_id
