#!/usr/bin/env python3
"""
Script pour visualiser les commandes enregistrées
Utile pour le restaurateur pour voir toutes les commandes
"""

import os
import json
from datetime import datetime
from pathlib import Path


def list_orders():
    """Liste toutes les commandes enregistrées"""
    orders_dir = Path("orders")

    if not orders_dir.exists():
        print("❌ Aucun dossier 'orders' trouvé")
        return

    # Lister tous les fichiers de commandes .txt
    txt_files = sorted(orders_dir.glob("commande_*.txt"), reverse=True)
    json_files = sorted(orders_dir.glob("conversation_*.json"), reverse=True)

    print("\n" + "=" * 70)
    print("📋 LISTE DES COMMANDES - FAMILY FOOD")
    print("=" * 70 + "\n")

    if not txt_files:
        print("Aucune commande trouvée.")
        return

    print(f"Total : {len(txt_files)} commande(s)\n")

    for i, filepath in enumerate(txt_files, 1):
        # Extraire les infos du nom de fichier
        filename = filepath.stem  # commande_CA161bfc_20260107_112830
        parts = filename.split("_")

        if len(parts) >= 4:
            call_sid = parts[1]
            date_str = parts[2]  # 20260107
            time_str = parts[3]  # 112830

            # Formater la date
            date_formatted = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
            time_formatted = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"

            print(f"{i}. 📝 Commande #{call_sid}")
            print(f"   📅 {date_formatted} à {time_formatted}")
            print(f"   📄 {filepath.name}")
            print()


def view_order(order_number=None):
    """Affiche le contenu d'une commande"""
    orders_dir = Path("orders")

    if not orders_dir.exists():
        print("❌ Aucun dossier 'orders' trouvé")
        return

    txt_files = sorted(orders_dir.glob("commande_*.txt"), reverse=True)

    if not txt_files:
        print("❌ Aucune commande trouvée")
        return

    if order_number is None:
        print("\n📋 Quelle commande voulez-vous voir ?")
        list_orders()
        try:
            order_number = int(input("\nNuméro de la commande (ou 0 pour annuler) : "))
            if order_number == 0:
                return
        except ValueError:
            print("❌ Numéro invalide")
            return

    if order_number < 1 or order_number > len(txt_files):
        print(f"❌ Numéro invalide. Choisissez entre 1 et {len(txt_files)}")
        return

    # Afficher la commande
    filepath = txt_files[order_number - 1]

    print("\n" + "=" * 70)
    with open(filepath, 'r', encoding='utf-8') as f:
        print(f.read())
    print("=" * 70 + "\n")


def view_latest():
    """Affiche la dernière commande"""
    orders_dir = Path("orders")

    if not orders_dir.exists():
        print("❌ Aucun dossier 'orders' trouvé")
        return

    txt_files = sorted(orders_dir.glob("commande_*.txt"), reverse=True)

    if not txt_files:
        print("❌ Aucune commande trouvée")
        return

    # Afficher la plus récente
    filepath = txt_files[0]

    print("\n" + "=" * 70)
    print("📋 DERNIÈRE COMMANDE")
    print("=" * 70)
    with open(filepath, 'r', encoding='utf-8') as f:
        print(f.read())
    print("=" * 70 + "\n")


def view_today():
    """Affiche toutes les commandes du jour"""
    orders_dir = Path("orders")

    if not orders_dir.exists():
        print("❌ Aucun dossier 'orders' trouvé")
        return

    today = datetime.now().strftime("%Y%m%d")
    txt_files = sorted(orders_dir.glob(f"commande_*_{today}_*.txt"), reverse=True)

    print("\n" + "=" * 70)
    print(f"📅 COMMANDES DU JOUR ({datetime.now().strftime('%d/%m/%Y')})")
    print("=" * 70 + "\n")

    if not txt_files:
        print("Aucune commande aujourd'hui.")
        return

    print(f"Total : {len(txt_files)} commande(s) aujourd'hui\n")

    for i, filepath in enumerate(txt_files, 1):
        print(f"\n{'=' * 70}")
        print(f"COMMANDE {i}/{len(txt_files)}")
        print("=" * 70)
        with open(filepath, 'r', encoding='utf-8') as f:
            print(f.read())
        print("=" * 70)


def export_summary():
    """Exporte un résumé de toutes les commandes"""
    orders_dir = Path("orders")

    if not orders_dir.exists():
        print("❌ Aucun dossier 'orders' trouvé")
        return

    json_files = sorted(orders_dir.glob("conversation_*.json"), reverse=True)

    if not json_files:
        print("❌ Aucune commande trouvée")
        return

    summary = []
    summary.append("=" * 80)
    summary.append(f"RÉSUMÉ DES COMMANDES - {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
    summary.append("=" * 80 + "\n")

    total_orders = 0
    total_amount = 0

    for filepath in json_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            call_sid = data.get("call_sid", "N/A")
            timestamp = data.get("timestamp", "")
            conversation = data.get("conversation", [])

            # Extraire le total
            for msg in reversed(conversation):
                if msg["role"] == "assistant" and "total" in msg.get("content", "").lower():
                    import re
                    match = re.search(r'total\s+(\d+(?:[.,]\d+)?)\s*euro', msg["content"].lower())
                    if match:
                        amount = float(match.group(1).replace(',', '.'))
                        total_amount += amount
                        break

            total_orders += 1

        except Exception as e:
            print(f"⚠️  Erreur lecture {filepath.name}: {e}")

    summary.append(f"📊 STATISTIQUES :")
    summary.append(f"   Total commandes : {total_orders}")
    summary.append(f"   Chiffre d'affaires : {total_amount:.2f} €")
    summary.append(f"   Panier moyen : {total_amount / total_orders:.2f} €" if total_orders > 0 else "")

    summary_text = "\n".join(summary)
    print("\n" + summary_text + "\n")

    # Sauvegarder le résumé
    summary_file = f"orders/resume_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_text)

    print(f"💾 Résumé sauvegardé : {summary_file}\n")


def main():
    """Menu principal"""
    while True:
        print("\n" + "=" * 70)
        print("📋 GESTION DES COMMANDES - FAMILY FOOD")
        print("=" * 70)
        print("\n1. 📋 Lister toutes les commandes")
        print("2. 👁️  Voir une commande")
        print("3. 🆕 Voir la dernière commande")
        print("4. 📅 Voir les commandes du jour")
        print("5. 📊 Exporter un résumé")
        print("0. 🚪 Quitter")

        try:
            choice = input("\nVotre choix : ").strip()

            if choice == "1":
                list_orders()
            elif choice == "2":
                view_order()
            elif choice == "3":
                view_latest()
            elif choice == "4":
                view_today()
            elif choice == "5":
                export_summary()
            elif choice == "0":
                print("\n👋 Au revoir !\n")
                break
            else:
                print("❌ Choix invalide")

        except KeyboardInterrupt:
            print("\n\n👋 Au revoir !\n")
            break


if __name__ == "__main__":
    main()