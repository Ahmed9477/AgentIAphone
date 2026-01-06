from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

# ==================== CONFIGURATION ====================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Initialiser OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ Client OpenAI initialisé")
except Exception as e:
    print(f"❌ Erreur OpenAI: {e}")
    client = None

# ==================== DONNÉES RESTAURANT ====================
RESTAURANT_DATA = {
    "info": {
        "nom": "Family Food",
        "type": "Fast-Food",
        "adresse": "Chanteloup-en-Brie, 77600",
        "telephone": "+33767021139"
    },

    "menu": {
        "burgers": [
            {"nom": "Classic", "prix": 8.50},
            {"nom": "Cheeseburger", "prix": 9.00},
            {"nom": "Bacon Burger", "prix": 10.50},
            {"nom": "Chicken Burger", "prix": 9.50},
            {"nom": "Fish Burger", "prix": 9.00},
            {"nom": "Veggie Burger", "prix": 8.50}
        ],
        "tacos": [
            {"nom": "Poulet", "prix": 7.50},
            {"nom": "Viande", "prix": 7.50},
            {"nom": "Mixte", "prix": 8.50},
            {"nom": "Cordon bleu", "prix": 8.00},
            {"nom": "XXL", "prix": 12.00}
        ],
        "sandwichs": [
            {"nom": "Panini Poulet", "prix": 6.50},
            {"nom": "Panini Jambon", "prix": 6.00},
            {"nom": "Américain", "prix": 7.00},
            {"nom": "Kebab", "prix": 7.50}
        ],
        "accompagnements": [
            {"nom": "Frites", "prix": 3.50},
            {"nom": "Grandes Frites", "prix": 4.50},
            {"nom": "Nuggets 6", "prix": 5.00},
            {"nom": "Onion Rings", "prix": 4.50}
        ]
    },

    "livraison": {
        "frais": 2.50,
        "temps": "25-35 minutes",
        "minimum": 12.00
    },

    "emporter": {
        "reduction": 10,
        "temps": "15-20 minutes"
    }
}

# Stockage
conversations = {}
commandes = {}

# ==================== IA ====================
def get_ai_response(history, user_input):
    """Obtenir réponse GPT-4o optimisée"""

    system_message = f"""Tu es employé chez Family Food, fast-food français à Chanteloup-en-Brie.

🍔 MENU COMPLET:
Burgers: Classic 8.50€, Cheese 9€, Bacon 10.50€, Chicken 9.50€, Fish 9€, Veggie 8.50€
Tacos: Poulet 7.50€, Viande 7.50€, Mixte 8.50€, Cordon bleu 8€, XXL 12€
Sandwichs: Panini poulet 6.50€, Panini jambon 6€, Américain 7€, KEBAB 7.50€
Accompagnements: Frites 3.50€, Grandes frites 4.50€, Nuggets 5€, Onion rings 4.50€

🎯 OBJECTIF: Collecter toutes les infos pour finaliser une commande.

📋 INFOS NÉCESSAIRES (collecte intelligente):
1. Articles + options (pain/galette, sauces, taille...)
2. Livraison ou emporter ?
3. Nom
4. Téléphone  
5. Si livraison → Adresse
6. Paiement espèces ou carte
7. Récapitulatif complet + prix total + temps
8. Confirmation
9. "À tout à l'heure" puis attendre au revoir
10. Quand client dit au revoir/merci → "Bonne journée ! END_CALL"

⚡ RÈGLES:
- Réponses COURTES (10-15 mots max)
- UNE question à la fois
- Prix UNIQUEMENT dans le récapitulatif final
- Adapte-toi : si client donne plusieurs infos d'un coup, prends-les
- Sois naturel, enthousiaste, humain
- Si au revoir/merci → "Bonne journée ! END_CALL"

💡 INFOS:
- Livraison: 2.50€, 25-35min, minimum 12€
- Emporter: -10%, 15-20min

🧠 GÈRE INTELLIGEMMENT:
- Identifie ce qui manque
- Pose la prochaine question logique
- Ne redemande pas ce que tu as déjà
- Sois efficace et rapide"""

    messages = [{"role": "system", "content": system_message}]
    messages.extend(history[-6:])  # 6 derniers messages
    messages.append({"role": "user", "content": user_input})

    try:
        if client is None:
            return "Problème technique. Réessayez."

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.3,
            max_tokens=80,
            timeout=3
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"❌ Erreur: {e}")
        return "Désolé, problème technique. Répétez ?"

# ==================== ROUTES ====================
@app.route("/voice", methods=["POST"])
def voice():
    """Point d'entrée"""
    response = VoiceResponse()

    response.say(
        '<speak>Bonjour <break time="200ms"/> Family Food, je vous écoute.</speak>',
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    gather = Gather(
        input="speech",
        language="fr-FR",
        speechTimeout="3",
        action="/process",
        method="POST",
        bargeIn=True,
        timeout=15,
        hints="burger, tacos, kebab, menu, livraison, emporter, espèces, carte"
    )
    response.append(gather)

    return Response(str(response), mimetype="text/xml")

@app.route("/process", methods=["POST"])
def process():
    """Traiter la parole"""

    speech = request.values.get("SpeechResult", "")
    call_sid = request.values.get("CallSid", "")

    print(f"👤 Client: {speech}")

    # Initialiser conversation
    if call_sid not in conversations:
        conversations[call_sid] = []

    conv = conversations[call_sid]

    # Obtenir réponse IA
    ai_reply = get_ai_response(conv, speech)

    print(f"🤖 IA: {ai_reply}")

    # Sauvegarder historique
    conv.append({"role": "user", "content": speech})
    conv.append({"role": "assistant", "content": ai_reply})

    # Vérifier fin d'appel
    if "END_CALL" in ai_reply:
        clean_reply = ai_reply.replace("END_CALL", "").strip()

        response = VoiceResponse()
        response.say(
            f'<speak>{clean_reply}</speak>',
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )
        print("📴 Fin d'appel")
        return Response(str(response), mimetype="text/xml")

    # Réponse normale
    response = VoiceResponse()
    response.say(
        f'<speak><prosody rate="medium">{ai_reply}</prosody></speak>',
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    # Continuer à écouter
    gather = Gather(
        input="speech",
        language="fr-FR",
        speechTimeout="3",
        action="/process",
        method="POST",
        timeout=15,
        bargeIn=True,
        hints="burger, tacos, kebab, frites, oui, non, livraison, emporter, blanche, harissa, algérienne, barbecue, espèces, carte"
    )
    response.append(gather)

    # Si timeout → 2ème chance
    gather_retry = Gather(
        input="speech",
        language="fr-FR",
        speechTimeout="3",
        action="/process",
        method="POST",
        timeout=15,
        bargeIn=True
    )

    response.say(
        "Vous êtes toujours là ? Je vous écoute.",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )
    response.append(gather_retry)

    return Response(str(response), mimetype="text/xml")

# ==================== API ====================
@app.route("/")
def home():
    """Page d'accueil"""
    return jsonify({
        "service": "Agent IA Family Food",
        "restaurant": RESTAURANT_DATA["info"]["nom"],
        "status": "actif ✅",
        "version": "optimisée",
        "features": [
            "Voix naturelle masculine",
            "IA autonome et intelligente",
            "Interruption possible (bargeIn)",
            "Timeout 15s (confortable)",
            "Gestion fin d'appel automatique"
        ]
    })

@app.route("/api/menu")
def api_menu():
    """Menu complet"""
    return jsonify(RESTAURANT_DATA["menu"])

@app.route("/api/commandes")
def api_commandes():
    """Liste des commandes"""
    return jsonify({
        "total": len(commandes),
        "commandes": list(commandes.values())
    })

@app.route("/api/conversations")
def api_conversations():
    """Conversations actives"""
    return jsonify({
        "total": len(conversations),
        "actives": len([c for c in conversations.values() if len(c) > 0])
    })

@app.route("/api/clear", methods=["POST"])
def clear_cache():
    """Vider le cache"""
    global conversations, commandes
    conversations = {}
    commandes = {}
    return jsonify({"success": True, "message": "Cache vidé"})

# ==================== DÉMARRAGE ====================
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🍔 AGENT IA FAMILY FOOD - VERSION OPTIMISÉE")
    print("=" * 70)
    print(f"\n📍 Restaurant: {RESTAURANT_DATA['info']['nom']}")
    print(f"📞 Téléphone: {RESTAURANT_DATA['info']['telephone']}")
    print(f"🏠 Adresse: {RESTAURANT_DATA['info']['adresse']}")
    print("\n✨ FONCTIONNALITÉS:")
    print("   ✅ IA autonome et intelligente")
    print("   ✅ Voix masculine naturelle (Google Neural2-B)")
    print("   ✅ Interruption possible pendant la conversation")
    print("   ✅ Timeout confortable (15 secondes)")
    print("   ✅ Gestion automatique de fin d'appel")
    print("   ✅ Collecte intelligente des informations")
    print("\n📋 MENU DISPONIBLE:")
    print(f"   • {len(RESTAURANT_DATA['menu']['burgers'])} Burgers")
    print(f"   • {len(RESTAURANT_DATA['menu']['tacos'])} Tacos")
    print(f"   • {len(RESTAURANT_DATA['menu']['sandwichs'])} Sandwichs (dont Kebab)")
    print(f"   • {len(RESTAURANT_DATA['menu']['accompagnements'])} Accompagnements")
    print("\n🚀 Serveur: http://localhost:5000")
    print("🔍 APIs:")
    print("   • /api/menu - Menu complet")
    print("   • /api/commandes - Liste des commandes")
    print("   • /api/conversations - Conversations actives")
    print("\n⚡ PERFORMANCE:")
    print("   • Latence: ~2-3 secondes")
    print("   • Coût: ~0,10€ par appel")
    print("   • Fiabilité: Excellente")
    print("\n" + "=" * 70 + "\n")

    app.run(debug=True, port=5000, host="0.0.0.0")