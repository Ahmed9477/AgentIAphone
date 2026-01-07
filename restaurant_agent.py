from flask import Flask, request, Response, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from openai import OpenAI
import json
from datetime import datetime
import os
from dotenv import load_dotenv
from restaurant_config import RESTAURANT_NAME, RESTAURANT_DATA

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MEMORY_TIMEOUT = int(os.getenv("MEMORY_TIMEOUT", "1800"))  # 30 minutes

# Initialiser OpenAI
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ Client OpenAI initialisé avec succès")
except Exception as e:
    print(f"❌ Erreur lors de l'initialisation OpenAI: {e}")
    client = None

# Stockage des conversations avec timestamps
conversations = {}  # {call_sid: [{"role": str, "content": str, "time": datetime}]}


# ==================== FONCTIONS UTILITAIRES ====================

def cleanup_old_conversations():
    """Nettoie les conversations expirées ou trop longues"""
    now = datetime.now()
    to_delete = []

    for call_sid, conv in conversations.items():
        if not conv:
            to_delete.append(call_sid)
            continue

        # Supprimer SEULEMENT si conversation trop longue (plus de 50 messages)
        # Augmenté de 30 à 50 pour éviter de supprimer pendant un appel actif
        if len(conv) > 50:
            to_delete.append(call_sid)
            continue

        # Supprimer si dernier message trop ancien (30 minutes)
        last_message_time = conv[-1].get("time", now)
        if (now - last_message_time).seconds > MEMORY_TIMEOUT:
            to_delete.append(call_sid)

    for sid in to_delete:
        print(f"🗑️  Nettoyage conversation: {sid}")
        del conversations[sid]

    if to_delete:
        print(f"✅ {len(to_delete)} conversation(s) nettoyée(s)")


def detect_conversation_stage(history):
    """Détecte automatiquement l'étape de la conversation"""
    if len(history) < 4:
        return "commande"  # Prise de commande
    elif len(history) < 8:
        return "livraison"  # Type de livraison
    elif len(history) < 12:
        return "infos_client"  # Infos client
    else:
        return "finalisation"  # Finalisation


def extract_order_summary(history):
    """Extrait un résumé des articles commandés"""
    user_messages = [msg["content"] for msg in history if msg["role"] == "user"]

    if not user_messages:
        return "Nouvelle commande"

    # Prendre les 3 premiers messages utilisateur pour le contexte
    recent = " ".join(user_messages[:3])
    return recent[:100] + "..." if len(recent) > 100 else recent


def build_menu_context():
    """Construit le contexte du menu pour l'IA"""
    menu_items = []

    for category, items in RESTAURANT_DATA["menu"].items():
        category_name = category.capitalize()
        for item in items:
            # Ignorer les redirections (comme "Grec" qui pointe vers "Kebab")
            if "redirect" not in item:
                menu_items.append(f"{item['nom']} ({item['prix']}€)")

    sauces = ", ".join(RESTAURANT_DATA["sauces"])
    crudites = ", ".join(RESTAURANT_DATA["crudites"])

    return f"""
MENU DISPONIBLE:
{', '.join(menu_items[:15])}... et plus

IMPORTANT: "Grec" = "Kebab" (même produit)

MENUS COMPLETS:
• Menu Kebab/Grec: 9.50€ (Kebab + Boisson)
• Menu Burger: 12.50€ (Burger + Frites + Boisson)
• Menu Tacos: 10.50€ (Tacos + Frites + Boisson)

SAUCES: {sauces}
CRUDITÉS: {crudites}

SERVICES:
• Livraison: +{RESTAURANT_DATA['services']['livraison']['frais']}€, min {RESTAURANT_DATA['services']['livraison']['minimum']}€
• Emporter: -{RESTAURANT_DATA['services']['emporter']['reduction']}%
• Sur place

PAIEMENTS: {', '.join(RESTAURANT_DATA['paiements'])}

SUPPLÉMENTS:
• Fromage: +1€
• Extra viande: +2€
"""


def get_ai_response(history, user_input):
    """
    Génère une réponse IA avec mémoire contextuelle

    Args:
        history: Historique de la conversation (sans le dernier message user)
        user_input: Dernier message de l'utilisateur

    Returns:
        str: Réponse de l'assistant
    """

    # Détection automatique de l'étape
    stage = detect_conversation_stage(history)
    order_summary = extract_order_summary(history)

    # Construire le menu pour le contexte
    menu_context = build_menu_context()

    # Construction du prompt système adaptatif
    system_prompt = f"""Tu es l'assistant vocal de {RESTAURANT_NAME}, {RESTAURANT_DATA['info']['type']}.

📋 CONTEXTE ACTUEL:
• Commande en cours: {order_summary}
• Étape: {stage}
• Historique: {len(history)} messages

{menu_context}

🎯 TON RÔLE - ÉTAPES PRÉCISES:

1. COMMANDE INITIALE:
   - Demander "Que souhaitez-vous commander?"
   - Si client dit "kebab" ou "grec" → c'est la même chose (Kebab à 7.50€)
   - Proposer TOUJOURS le menu: "Souhaitez-vous prendre un menu avec boisson?"

2. SI MENU KEBAB/GREC (9.50€):
   - Sauce: "Quelle sauce?" (NE PAS LISTER TOUTES LES SAUCES, sauf si demandé)
   - Crudités: "Quelles crudités?" (NE PAS LISTER, sauf si demandé)
   - Boisson: "Quelle boisson?" (NE PAS LISTER, sauf si demandé)
   - Options: "Des suppléments?" (NE PAS LISTER les prix, sauf si demandé)

   ⚠️ IMPORTANT: Ne liste les options que si le client demande "Quoi comme sauces?" ou "Lesquelles?"

3. SI MENU TACOS (10.50€):
   - Type de viande: "Quel tacos?" (Poulet, Viande, Mixte, Cordon Bleu, XXL)
   - Sauce: "Quelle sauce?"
   - Crudités: "Quelles crudités?" ou "sans X"
   - Boisson: "Quelle boisson?"
   - Options: "Des suppléments?"

4. SI KEBAB/GREC SEUL (7.50€):
   - Sauce: "Quelle sauce?"
   - Crudités: "Quelles crudités?" ou noter "sans X"
   - Options: "Des suppléments?"

4. APRÈS CHAQUE ARTICLE:
   - TOUJOURS dire: "Ça sera tout?" ou "Autre chose?"
   - JAMAIS dire "Combien voulez-vous?"
   - Si client dit "oui" ou "c'est bon" → passer à la livraison
   - Si client ajoute autre chose → recommencer depuis étape 1

5. TYPE DE COMMANDE:
   - "Sur place, à emporter ou livraison?"

6. INFOS CLIENT:
   - Nom
   - Téléphone
   - Si livraison: Adresse complète

7. PAIEMENT (OBLIGATOIRE):
   - "Espèces, carte ou ticket restaurant?"
   - NE JAMAIS OUBLIER CETTE ÉTAPE

8. RÉCAPITULATIF FINAL (TRÈS IMPORTANT):
   - Liste TOUS les articles commandés avec TOUS les détails
   - Pour chaque article : 
     * Si MENU : "Menu [Article]" (ex: Menu Kebab, Menu Tacos, Menu Burger)
     * Type de viande (si tacos)
     * TOUTES les sauces mentionnées
     * TOUTES les crudités ou "sans crudités"
     * Boisson (si menu)
   - Total calculé précisément AVANT réduction
   - Si emporter : mentionner la réduction -10% et calculer le nouveau total
   - Type de commande
   - Infos client
   - Paiement
   - Format : "Menu Kebab sauce X, crudités Y, boisson Z. À emporter avec -10%. Total initial A€, après réduction B€. Paiement C. Merci! Prêt dans X minutes. END_CALL"

✅ RÈGLES STRICTES:
• Maximum 12 mots par réponse (sauf si client demande la liste)
• TOUJOURS proposer le menu au début
• Dire "Ça sera tout?" après chaque article, PAS "Combien?"
• "Grec" = "Kebab" (même chose)
• Questions COURTES : "Quelle sauce?", "Quelle boisson?", "Quelles crudités?"
• Lister les options UNIQUEMENT si le client demande "Lesquelles?" ou "Quoi comme...?"
• Remplir toutes les cases: sauce, crudités, boisson (si menu), options
• Ton chaleureux et naturel comme dans un vrai restaurant
• Se souvenir de TOUT ce qui a été dit pendant TOUT L'APPEL
• JAMAIS oublier la commande en cours

🥤 GESTION DES BOISSONS SUPPLÉMENTAIRES:
• Si client dit "une autre boisson" ou "ajouter une boisson" APRÈS avoir déjà choisi une boisson de menu
• TOUJOURS clarifier : "Souhaitez-vous changer la boisson du menu ou ajouter une boisson supplémentaire ?"
• Si AJOUTER : préciser le prix (2.50€ par boisson)
• Si CHANGER : remplacer la boisson du menu (inclus dans le prix)
• Dans le récap : distinguer "boisson du menu" et "boissons supplémentaires"

❌ INTERDICTIONS:
• Ne JAMAIS demander "Combien voulez-vous?"
• Ne JAMAIS dire "Combien de X?"
• Ne JAMAIS oublier de proposer le menu
• Ne pas accepter des articles qui n'existent pas (vérifier le menu)
• Ne pas inventer de prix
• Ne JAMAIS oublier "Menu" dans le récapitulatif si c'est un menu
• Ne JAMAIS oublier la boisson dans le récapitulatif si c'est un menu
• Ne pas appliquer de réduction sans le mentionner clairement
• TOUJOURS calculer à partir du prix du menu (9.50€ kebab, 10.50€ tacos, 12.50€ burger)
• Si boisson seule demandée : prix 2.50€, PAS dans un menu

📝 EXEMPLE DE CONVERSATION PARFAITE:
Client: "Un grec"
Toi: "Menu avec boisson?" (PAS de prix)

Client: "Oui"
Toi: "Quelle sauce?" (PAS de liste)

Client: "Lesquelles vous avez?"
Toi: "Blanche, Harissa, Algérienne, Barbecue, Mayo, Ketchup, Curry, Samouraï, Andalouse"

Client: "Algérienne"
Toi: "Quelles crudités?"

Client: "Tout sauf oignons"
Toi: "Quelle boisson?"

Client: "Ice Tea"
Toi: "Des suppléments?"

Client: "Non"
Toi: "Ça sera tout?"

Client: "Oui"
Toi: "Sur place, emporter ou livraison?"

Client: "Livraison"
Toi: "Votre nom?"

Client: "Ahmed"
Toi: "Votre téléphone?"

Client: "0612345678"
Toi: "Votre adresse?"

Client: "5 rue de Paris"
Toi: "Espèces, carte ou ticket restaurant?"

Client: "Carte"
Toi: "Menu Kebab sauce algérienne, sans oignons, Ice Tea, livraison 5 rue de Paris, Ahmed 0612345678, carte. Total 12 euros. Merci! Prêt dans 30 minutes. END_CALL"
"""

    # Construction des messages pour l'API
    messages = [{"role": "system", "content": system_prompt}]

    # Ajouter les 10 derniers messages de l'historique (pour ne pas dépasser le contexte)
    messages.extend([
        {"role": msg["role"], "content": msg["content"]}
        for msg in history[-10:]
    ])

    # Ajouter le message actuel de l'utilisateur
    messages.append({"role": "user", "content": user_input})

    try:
        if client is None:
            return "Service temporairement indisponible. Veuillez rappeler."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,  # Un peu de créativité mais reste cohérent
            max_tokens=80,  # Limiter la longueur
            timeout=3  # Timeout de 3 secondes
        )

        ai_reply = response.choices[0].message.content.strip()

        # Nettoyage de la réponse
        ai_reply = ai_reply.replace('"', '').replace('*', '')

        return ai_reply

    except Exception as e:
        print(f"❌ Erreur API OpenAI: {e}")

        # Réponse de secours selon l'étape
        fallback_responses = {
            "commande": "Que souhaitez-vous commander?",
            "livraison": "Sur place, emporter ou livraison?",
            "infos_client": "Votre nom et téléphone?",
            "finalisation": "Espèces ou carte?"
        }

        return fallback_responses.get(stage, "Pouvez-vous répéter?")


# ==================== ROUTES VOCALES ====================

@app.route("/voice", methods=["POST"])
def voice():
    """Point d'entrée initial de l'appel"""

    call_sid = request.values.get("CallSid", "unknown")[:8]
    caller = request.values.get("From", "inconnu")

    print(f"\n📞 NOUVEL APPEL - CallSid: {call_sid} - De: {caller}")

    response = VoiceResponse()
    response.say(
        f"Bonjour, bienvenue chez {RESTAURANT_NAME}! Que souhaitez-vous commander?",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    # Gather pour capturer la réponse vocale
    gather = Gather(
        input="speech",
        language="fr-FR",
        speechTimeout="auto",  # Détection automatique de la fin de parole
        action="/process",
        method="POST",
        hints="pizza burger kebab tacos frites sandwich menu boisson livraison emporter",
        timeout=10
    )

    response.append(gather)

    # Si pas de réponse après le timeout
    response.say(
        "Je n'ai pas entendu votre réponse. Au revoir.",
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    return Response(str(response), mimetype="text/xml")


@app.route("/process", methods=["POST"])
def process():
    """Traite chaque réponse vocale du client"""

    speech = request.values.get("SpeechResult", "").strip()
    call_sid = request.values.get("CallSid", "unknown")[:8]
    confidence = request.values.get("Confidence", "0")

    print(f"\n📞 [{call_sid}] 👤 Client: '{speech}' (confiance: {confidence})")

    # Si pas de parole détectée
    if not speech:
        response = VoiceResponse()
        response.say(
            "Je n'ai pas compris. Pouvez-vous répéter?",
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )

        gather = Gather(
            input="speech",
            language="fr-FR",
            speechTimeout="auto",
            action="/process",
            method="POST",
            timeout=10
        )
        response.append(gather)

        return Response(str(response), mimetype="text/xml")

    # Initialiser la conversation si nécessaire
    if call_sid not in conversations:
        conversations[call_sid] = []

    conv = conversations[call_sid]

    # Ajouter le message utilisateur avec timestamp
    conv.append({
        "role": "user",
        "content": speech,
        "time": datetime.now()
    })

    # Obtenir la réponse de l'IA
    ai_reply = get_ai_response(conv[:-1], speech)

    print(f"📞 [{call_sid}] 🤖 Bot: '{ai_reply}'")

    # Ajouter la réponse du bot avec timestamp
    conv.append({
        "role": "assistant",
        "content": ai_reply,
        "time": datetime.now()
    })

    # Vérifier si c'est la fin de la conversation
    should_end = "END_CALL" in ai_reply.upper()

    # Retirer END_CALL de la réponse vocale
    ai_reply_clean = ai_reply.replace("END_CALL", "").replace("end_call", "").strip()

    response = VoiceResponse()
    response.say(
        ai_reply_clean,
        language="fr-FR",
        voice="Google.fr-FR-Neural2-B"
    )

    if should_end:
        # Terminer l'appel
        print(f"📴 [{call_sid}] ✅ APPEL TERMINÉ - Commande complète")
        response.hangup()

        # Sauvegarder la commande complète (optionnel)
        save_order(call_sid, conv)
    else:
        # Continuer la conversation
        gather = Gather(
            input="speech",
            language="fr-FR",
            speechTimeout="auto",
            action="/process",
            method="POST",
            timeout=10
        )
        response.append(gather)

        # Message si timeout
        response.say(
            "Êtes-vous toujours là? Au revoir.",
            language="fr-FR",
            voice="Google.fr-FR-Neural2-B"
        )

    # Nettoyage périodique
    cleanup_old_conversations()

    return Response(str(response), mimetype="text/xml")


def save_order(call_sid, conversation):
    """Sauvegarde la commande finale (optionnel)"""
    try:
        # Créer le dossier orders s'il n'existe pas
        os.makedirs("orders", exist_ok=True)

        timestamp = datetime.now()
        date_str = timestamp.strftime('%Y%m%d_%H%M%S')

        # 1. Sauvegarder la conversation complète (JSON technique)
        order_data = {
            "call_sid": call_sid,
            "timestamp": timestamp.isoformat(),
            "conversation": conversation
        }

        filename_json = f"orders/conversation_{call_sid}_{date_str}.json"
        with open(filename_json, 'w', encoding='utf-8') as f:
            json.dump(order_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"💾 Conversation sauvegardée: {filename_json}")

        # 2. Créer un fichier lisible pour le restaurateur
        order_summary = extract_order_from_conversation(conversation, call_sid, timestamp)

        filename_txt = f"orders/commande_{call_sid}_{date_str}.txt"
        with open(filename_txt, 'w', encoding='utf-8') as f:
            f.write(order_summary)

        print(f"📄 Bon de commande créé: {filename_txt}")

    except Exception as e:
        print(f"⚠️  Erreur sauvegarde commande: {e}")


def extract_order_from_conversation(conversation, call_sid, timestamp):
    """Extrait les informations importantes de la conversation pour créer un bon de commande"""

    # Extraire les infos de la conversation
    client_name = ""
    client_phone = ""
    client_address = ""
    delivery_type = ""
    payment_method = ""

    # Parser la conversation pour extraire les infos
    for i, msg in enumerate(conversation):
        content = msg.get("content", "").lower()

        # Détecter le nom
        if i > 0 and "nom" in conversation[i - 1].get("content", "").lower():
            if msg["role"] == "user":
                client_name = msg["content"]

        # Détecter le téléphone
        if i > 0 and "téléphone" in conversation[i - 1].get("content", "").lower():
            if msg["role"] == "user":
                client_phone = msg["content"]

        # Détecter l'adresse
        if i > 0 and "adresse" in conversation[i - 1].get("content", "").lower():
            if msg["role"] == "user":
                client_address = msg["content"]

        # Détecter le type de commande
        if msg["role"] == "user":
            if "livraison" in content:
                delivery_type = "Livraison"
            elif "emporter" in content or "à emporter" in content:
                delivery_type = "À emporter"
            elif "sur place" in content:
                delivery_type = "Sur place"

        # Détecter le paiement
        if msg["role"] == "user" and i > 0:
            prev_content = conversation[i - 1].get("content", "").lower()
            if "paiement" in prev_content or "espèce" in prev_content or "carte" in prev_content:
                if "carte" in content:
                    payment_method = "Carte bancaire"
                elif "espèce" in content:
                    payment_method = "Espèces"
                elif "ticket" in content:
                    payment_method = "Ticket restaurant"

    # Extraire les articles et le total du récapitulatif final
    order_items = []
    total = ""
    initial_total = ""
    discount_info = ""

    for msg in reversed(conversation):
        if msg["role"] == "assistant" and "END_CALL" in msg.get("content", ""):
            recap = msg["content"]

            # Extraire le total
            import re

            # Chercher "Total initial X€, après réduction Y€"
            reduction_match = re.search(
                r'total initial\s+(\d+(?:[.,]\d+)?)\s*€.*après réduction\s+(\d+(?:[.,]\d+)?)\s*€', recap.lower())
            if reduction_match:
                initial_total = reduction_match.group(1).replace(',', '.') + " €"
                total = reduction_match.group(2).replace(',', '.') + " €"
                discount_info = " (réduction -10% appliquée)"
            else:
                # Chercher "Total X euros" ou "Total: X€"
                total_match = re.search(r'total\s*:?\s*(\d+(?:[.,]\d+)?)\s*(?:euros?|€)', recap.lower())
                if total_match:
                    total = total_match.group(1).replace(',', '.') + " €"

            # Parser le récapitulatif pour extraire les articles
            recap_clean = recap.replace("Récapitulatif:", "").replace("Récapitulatif de votre commande :", "").replace(
                "END_CALL", "").strip()

            # Retirer la partie après "Total"
            if "Total" in recap_clean or "total" in recap_clean:
                recap_items = re.split(r'[Tt]otal', recap_clean)[0].strip()
            else:
                recap_items = recap_clean

            # Retirer aussi les remerciements
            recap_items = re.split(r'[Mm]erci', recap_items)[0].strip()

            # Parser les segments (séparés par des points)
            segments = recap_items.split('.')

            for segment in segments:
                segment = segment.strip()
                # Ignorer les segments vides ou trop courts
                if not segment or len(segment) < 5:
                    continue

                # Ignorer les infos client, paiement, etc.
                skip_keywords = ['votre', 'sera', 'prêt', 'minute', 'merci', 'paiement',
                                 'espèces', 'carte', 'ticket', 'livraison au', 'emporter',
                                 'sur place', 'nom', 'téléphone', 'adresse']

                if any(keyword in segment.lower() for keyword in skip_keywords):
                    continue

                # C'est probablement un article
                # Capitaliser la première lettre
                if segment:
                    order_items.append(segment[0].upper() + segment[1:])

            break

    # Si pas d'items trouvés, essayer une extraction plus simple
    if not order_items:
        for msg in reversed(conversation):
            if msg["role"] == "assistant" and "END_CALL" in msg.get("content", ""):
                recap = msg["content"]
                # Chercher les lignes qui commencent par "-"
                lines = recap.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('-'):
                        cleaned = line[1:].strip()
                        if cleaned and len(cleaned) > 5:
                            order_items.append(cleaned.capitalize())
                break

    # Construire le bon de commande
    bon = []
    bon.append("=" * 60)
    bon.append(f"         {RESTAURANT_NAME.upper()}")
    bon.append(f"           BON DE COMMANDE #{call_sid}")
    bon.append("=" * 60)
    bon.append(f"Date/Heure : {timestamp.strftime('%d/%m/%Y à %H:%M:%S')}")
    bon.append("")

    # Informations client
    bon.append("CLIENT :")
    bon.append(f"  Nom       : {client_name or 'Non renseigné'}")
    bon.append(f"  Téléphone : {client_phone or 'Non renseigné'}")
    if client_address:
        bon.append(f"  Adresse   : {client_address}")
    bon.append("")

    # Type de commande
    bon.append(f"TYPE : {delivery_type or 'Non renseigné'}")
    bon.append("")

    # Détails de la commande
    bon.append("COMMANDE :")
    bon.append("-" * 60)

    if order_items:
        for i, item in enumerate(order_items, 1):
            bon.append(f"  {i}. {item}")
    else:
        bon.append("  [Voir conversation pour détails]")

    bon.append("-" * 60)
    bon.append("")

    # Total
    if initial_total and discount_info:
        bon.append(f"SOUS-TOTAL : {initial_total}")
        bon.append(f"RÉDUCTION : -10% (à emporter)")
        bon.append(f"TOTAL : {total}")
    else:
        bon.append(f"TOTAL : {total}" if total else "TOTAL : Voir récapitulatif")
    bon.append("")

    # Paiement
    bon.append(f"PAIEMENT : {payment_method or 'Non renseigné'}")
    bon.append("")

    # Temps estimé
    if delivery_type:
        if "livraison" in delivery_type.lower():
            temps = RESTAURANT_DATA["services"]["livraison"]["temps"]
        elif "emporter" in delivery_type.lower():
            temps = RESTAURANT_DATA["services"]["emporter"]["temps"]
        else:
            temps = RESTAURANT_DATA["services"]["sur_place"]["temps"]
        bon.append(f"TEMPS ESTIMÉ : {temps}")

    bon.append("")
    bon.append("=" * 60)
    bon.append(f"Contact : {RESTAURANT_DATA['info']['telephone']}")
    bon.append(f"Adresse : {RESTAURANT_DATA['info']['adresse']}")
    bon.append("=" * 60)

    return "\n".join(bon)


# ==================== ROUTES API ====================

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def home():
    """Page d'accueil / Health check"""
    cleanup_old_conversations()

    return jsonify({
        "status": "online",
        "restaurant": RESTAURANT_NAME,
        "active_conversations": len(conversations),
        "ai_enabled": client is not None,
        "version": "2.0"
    })


@app.route("/api/stats", methods=["GET"])
def stats():
    """Statistiques du serveur"""
    cleanup_old_conversations()

    return jsonify({
        "restaurant": RESTAURANT_NAME,
        "conversations_actives": len(conversations),
        "total_messages": sum(len(conv) for conv in conversations.values()),
        "ai_status": "active" if client else "inactive"
    })


@app.route("/api/conversations", methods=["GET"])
def get_conversations():
    """Liste toutes les conversations actives"""
    cleanup_old_conversations()

    conversations_list = []
    for call_sid, conv in conversations.items():
        conversations_list.append({
            "call_sid": call_sid,
            "messages": len(conv),
            "last_activity": conv[-1]["time"].isoformat() if conv else None
        })

    return jsonify(conversations_list)


@app.route("/clear", methods=["POST"])
def clear():
    """Efface toutes les conversations"""
    global conversations
    count = len(conversations)
    conversations.clear()
    print(f"🗑️  {count} conversation(s) effacée(s)")

    return jsonify({
        "cleared": True,
        "count": count
    })


# ==================== MIDDLEWARE ====================

@app.after_request
def after_request(response):
    """Nettoyage automatique après chaque requête"""
    # NE NETTOYER QUE toutes les 10 requêtes pour éviter de supprimer pendant un appel
    if not hasattr(app, 'request_count'):
        app.request_count = 0

    app.request_count += 1

    # Nettoyer seulement toutes les 10 requêtes
    if app.request_count % 10 == 0:
        cleanup_old_conversations()

    return response


# ==================== LANCEMENT ====================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🍔 AGENT IA RESTAURANT - SYSTÈME VOCAL INTELLIGENT")
    print("=" * 60)
    print(f"🏪 Restaurant: {RESTAURANT_NAME}")
    print(f"🤖 IA: {'✅ Active (OpenAI)' if client else '❌ Inactive'}")
    print(f"🧠 Mémoire: {MEMORY_TIMEOUT // 60} minutes")
    print(f"🌐 URL locale: http://localhost:5000")
    print(f"📞 Webhook: http://votre-ngrok.com/voice")
    print("=" * 60)
    print("\n🚀 Serveur démarré - En attente d'appels...\n")

    app.run(debug=True, port=5000, host="0.0.0.0")