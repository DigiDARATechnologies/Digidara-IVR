from typing import List, Optional, Dict, Any
from app.schemas.campaign import CampaignCreate, CampaignUpdate

def row_to_dict(row: Any) -> Dict[str, Any]:
    """Helper to convert a row object to a standard Python dictionary."""
    return dict(row) if row else {}

def get_campaign_by_id(
    conn: Any, campaign_id: int, organization_id: int,
) -> Optional[Dict[str, Any]]:
    """Retrieves a single campaign by its database ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT id, organization_id, campaign_name, objective, ai_prompt FROM campaigns WHERE id = %s AND organization_id = %s", (campaign_id, organization_id))
    row = cursor.fetchone()
    if row:
        return row_to_dict(row)
    return None

def get_all_campaigns(
    conn: Any, organization_id: int, skip: int = 0, limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves a list of all campaigns with pagination."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, organization_id, campaign_name, objective, ai_prompt FROM campaigns WHERE organization_id=%s ORDER BY id DESC LIMIT %s OFFSET %s",
        (organization_id, limit, skip)
    )
    rows = cursor.fetchall()
    return [row_to_dict(row) for row in rows]

def create_campaign(
    conn: Any, organization_id: int, campaign_in: CampaignCreate,
) -> Dict[str, Any]:
    """Inserts a new campaign."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO campaigns (organization_id,campaign_name,objective,ai_prompt) "
        "VALUES (%s,%s,%s,%s)",
        (organization_id, campaign_in.campaign_name, campaign_in.objective, campaign_in.ai_prompt)
    )
    conn.commit()
    new_id = cursor.lastrowid
    
    # Retrieve and return the created campaign
    return get_campaign_by_id(conn, new_id, organization_id)

def update_campaign(
    conn: Any, campaign_id: int, organization_id: int, campaign_in: CampaignUpdate,
) -> Optional[Dict[str, Any]]:
    """Updates selected fields of an existing campaign."""
    # Check if the campaign exists first
    existing = get_campaign_by_id(conn, campaign_id, organization_id)
    if not existing:
        return None

    update_data = campaign_in.model_dump(exclude_unset=True)
    if not update_data:
        return existing

    fields = []
    values = []
    for key, val in update_data.items():
        fields.append(f"{key} = %s")
        values.append(val)
    
    values.extend((campaign_id, organization_id))
    query = f"UPDATE campaigns SET {', '.join(fields)} WHERE id = %s AND organization_id = %s"
    
    cursor = conn.cursor()
    cursor.execute(query, tuple(values))
    conn.commit()

    return get_campaign_by_id(conn, campaign_id, organization_id)

def delete_campaign(conn: Any, campaign_id: int, organization_id: int) -> bool:
    """Deletes a campaign by ID. Returns True if successfully deleted, False if campaign didn't exist."""
    existing = get_campaign_by_id(conn, campaign_id, organization_id)
    if not existing:
        return False
        
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM campaigns WHERE id = %s AND organization_id = %s",
        (campaign_id, organization_id),
    )
    conn.commit()
    return True


def get_campaign_prompt(
    conn: Any, campaign_id: int, organization_id: int,
) -> Optional[str]:
    """
    Returns the AI prompt for a campaign.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ai_prompt FROM campaigns WHERE id = %s AND organization_id = %s",
        (campaign_id, organization_id)
    )
    row = cursor.fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return row["ai_prompt"]
    return row[0]
