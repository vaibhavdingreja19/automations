import requests
import pandas as pd

# ==========================
# CONFIG
# ==========================
GITHUB_ORG = "JHDevOps"
PAT = "YOUR_PAT_HERE"   # <<<--- PUT YOUR PAT HERE
OUTPUT_FILE = "github_users_with_sso.xlsx"

REST_BASE = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"

headers = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json"
}


# --------------------------
# Helper: split full name
# --------------------------
def split_name(fullname: str):
    if not fullname:
        return "", ""
    parts = fullname.strip().split()
    first = parts[0]
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first, last


# --------------------------
# Step 1: get org members
# --------------------------
def get_org_members(org: str):
    members = []
    page = 1
    while True:
        url = f"{REST_BASE}/orgs/{org}/members"
        resp = requests.get(url, headers=headers,
                            params={"per_page": 100, "page": page})
        if resp.status_code != 200:
            raise RuntimeError(f"Error fetching members (page {page}): "
                               f"{resp.status_code} {resp.text}")

        batch = resp.json()
        if not batch:
            break

        members.extend(batch)
        page += 1

    return members


# --------------------------
# Step 2: details for a user
# --------------------------
def get_user_profile(login: str):
    url = f"{REST_BASE}/users/{login}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"Error fetching user {login}: "
                           f"{resp.status_code} {resp.text}")
    data = resp.json()
    email = data.get("email") or ""
    fullname = data.get("name") or ""
    first, last = split_name(fullname)
    return email, first, last


# --------------------------
# Step 3: SAML SSO identities (SSO ID)
# Uses GraphQL samlIdentityProvider.externalIdentities
# --------------------------
def get_sso_id_map(org: str):
    """
    Returns dict: { github_login: sso_nameId }
    """
    query = """
    query($org: String!, $cursor: String) {
      organization(login: $org) {
        samlIdentityProvider {
          externalIdentities(first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                user { login }
                samlIdentity { nameId }
              }
            }
          }
        }
      }
    }
    """

    sso_map = {}
    cursor = None

    while True:
        variables = {"org": org, "cursor": cursor}
        resp = requests.post(
            GRAPHQL_URL,
            headers=headers,
            json={"query": query, "variables": variables},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"GraphQL error: {resp.status_code} {resp.text}")

        payload = resp.json()
        # basic error check
        if "errors" in payload:
            raise RuntimeError(f"GraphQL errors: {payload['errors']}")

        org_data = payload.get("data", {}).get("organization")
        if not org_data:
            # no such org or no access
            break

        provider = org_data.get("samlIdentityProvider")
        if not provider:
            # org doesn't have SAML SSO configured
            break

        ext = provider["externalIdentities"]
        for edge in ext["edges"]:
            node = edge["node"]
            user = node["user"]
            saml = node["samlIdentity"]
            if user and saml:
                login = user["login"]
                name_id = saml.get("nameId") or ""
                if login and name_id:
                    sso_map[login] = name_id

        page_info = ext["pageInfo"]
        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]

    return sso_map


# --------------------------
# MAIN
# --------------------------
def main():
    print(f"Fetching members of org '{GITHUB_ORG}'...")
    members = get_org_members(GITHUB_ORG)
    print(f"Found {len(members)} members.")

    print("Fetching SSO identities via GraphQL...")
    sso_map = get_sso_id_map(GITHUB_ORG)
    print(f"Found {len(sso_map)} SSO identities.")

    rows = []

    for m in members:
        login = m["login"]
        print(f"Processing {login}...")

        email, first, last = get_user_profile(login)
        sso_id = sso_map.get(login, "")

        rows.append({
            "Username": login,
            "Email": email,
            "FirstName": first,
            "LastName": last,
            "SSOId": sso_id,
        })

    df = pd.DataFrame(rows)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"\nDone. Wrote {len(df)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
