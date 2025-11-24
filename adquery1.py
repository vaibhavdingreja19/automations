import requests
from requests_negotiate_sspi import HttpNegotiateAuth
from bs4 import BeautifulSoup

# Create a session that uses Windows Integrated Auth
session = requests.Session()
session.auth = HttpNegotiateAuth()   # uses your current domain login

BASE_URL = "https://jhinfatools.jhancock.com/activedirectory/ActiveDirectory.cgi"


def lookup_user(username: str, domain: str = "MFCGD"):
    """
    Call JHinfatools 'Find Users or Groups - Search by pattern'
    and return raw HTML response.
    """
    params = {
        "domain": domain,   # from dropdown
        "type": "User",     # from dropdown (User / Group)
        "pattern": username # what you type in the box (e.g. 'dingrva')
    }

    # verify=False only if your corp CA isn't trusted in Python.
    # If certs are fine, remove verify=False.
    resp = session.get(BASE_URL, params=params, timeout=15, verify=False)
    resp.raise_for_status()
    return resp.text


def parse_user_info(html: str):
    """
    Very simple parser: tries to extract 'domain\\username',
    display name and email from the results table.
    You may tweak this once you see exact HTML.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find the line that contains the user info.
    # In your screenshot it looks like a single <pre> or <font>/<tt> block.
    # We'll just grab the last line that has a backslash in it: 'MFCGD\\dingrva ...'
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    user_line = None
    for line in lines:
        if "\\" in line and "@" in line:  # crude but works for 'MFCGD\\dingrva ... email'
            user_line = line
            break

    if not user_line:
        return None

    parts = user_line.split()
    # Example line (approx):
    # "MFCGD\dingrva  Vaibhav Dingreja  /N/A513783/...  VDingreja@jhancock.com  US  ..."
    # We'll try to infer:
    # 0: domain\user
    # 1..n: display name (until we hit something with '@' or a slash)
    # last: email (something with '@')

    # domain and samAccountName
    domain_user = parts[0]
    domain, sam = domain_user.split("\\", 1)

    # email = first token that has '@'
    email = next((p for p in parts if "@" in p), None)

    # build display name from tokens between domain\user and email / slash path
    name_tokens = []
    for p in parts[1:]:
        if "@" in p or p.startswith("/") or "\\" in p:
            break
        name_tokens.append(p)

    display_name = " ".join(name_tokens) if name_tokens else None

    # try to split display name into first / last (simple heuristic)
    first_name = last_name = None
    if display_name:
        name_bits = display_name.split()
        if len(name_bits) == 1:
            first_name = name_bits[0]
        else:
            first_name = name_bits[0]
            last_name = " ".join(name_bits[1:])

    return {
        "domain": domain,
        "username": sam,
        "display_name": display_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "raw_line": user_line,
    }


if __name__ == "__main__":
    # 👇 change this to test other IDs
    user = "dingrva"

    html = lookup_user(user)
    info = parse_user_info(html)
    print(info)
