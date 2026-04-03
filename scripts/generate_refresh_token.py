"""
🔑 Générateur de Refresh Token Google OAuth
============================================
Exécute ce script sur ton PC local (pas sur Streamlit Cloud).

Étapes :
1. Lance ce script : python generate_refresh_token.py
2. Un navigateur s'ouvre — connecte-toi avec ton compte Google
3. Autorise l'accès à Google Drive
4. Le script affiche ton VRAI refresh_token (commence par 1//)
5. Copie ce refresh_token dans les secrets Streamlit Cloud
"""

import json

# Tes credentials OAuth
CLIENT_ID = "753074012441-meebd7v5501cmvbp30olhfv63rcs47ak.apps.googleusercontent.com"
CLIENT_SECRET = "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"

SCOPES = ["https://www.googleapis.com/auth/drive"]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ Module manquant. Installe-le avec :")
        print("   pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return

    # Créer le flow OAuth
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    # Ouvre le navigateur pour autoriser
    print("\n🌐 Un navigateur va s'ouvrir pour autoriser l'accès Google Drive...")
    print("   Connecte-toi avec ton compte Google et autorise l'accès.\n")

    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    print("\n" + "=" * 60)
    print("✅ REFRESH TOKEN OBTENU !")
    print("=" * 60)
    print(f"\nrefresh_token = \"{creds.refresh_token}\"")
    print(f"\n(access_token = \"{creds.token}\")")
    print("\n⚠️  Copie le refresh_token (celui qui commence par 1//)")
    print("   et mets-le dans les secrets Streamlit Cloud :")
    print("   [google_oauth]")
    print(f"   refresh_token = \"{creds.refresh_token}\"")
    print("=" * 60)


if __name__ == "__main__":
    main()