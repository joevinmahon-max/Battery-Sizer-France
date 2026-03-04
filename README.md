🔋 Battery Sizer – Simulation automatique
--
V1
03.03.2026
By JMN
--
📌 Description

Battery Sizer est une application développée avec Streamlit permettant de :

  📥 Importer des données énergétiques (GRD ou fichiers mensuels)
  🔎 Nettoyer et reconstruire automatiquement les profils Import / Export
  ⚙️ Simuler une batterie (capacité & puissance variables)
  💰 Calculer le gain annuel optimisé (HP/HC ou tarif unique)
  📊 Visualiser les résultats (SOC, Import/Export avant/après)
  🔋 Déterminer automatiquement la batterie optimale

L’objectif : dimensionner intelligemment une batterie domestique à partir de données réelles.

🚀 Fonctionnalités principales

1️⃣ Import intelligent des données

  Fichier unique Excel/CSV (GRD)
  12 fichiers mensuels (Huawei ou autre)
  
  Détection automatique :
    Ligne d’en-tête
    Colonnes Date / Import / Export
    Données cumulatives
    Données en kW ou kWh
    Doublons DST (heure hiver)  

2️⃣ Reconstruction automatique
Cas gérés :
  Données en kW → conversion en kWh
  Compteur cumulatif → différenciation
  Totaux mensuels → reconstruction annuelle
  Export mensuel uniquement → profil solaire 10h–16h

3️⃣ Gestion des tarifs
Deux modes :
  🔹 Tarif unique
    Prix import (CHF/kWh)
    Prix export (CHF/kWh)
  
  🔹 HP / HC
    Plages horaires configurables
    Week-end entièrement HC (option)
    Tarifs distincts Import HP / HC
    
    Sélection GRD prédéfinie :
      Groupe E
      Romande Energie
      Manuel

4️⃣ Simulation batterie

Simulation complète :
  Capacité (kWh)
  Puissance (kW)
  SOC minimum
  Rendement aller-retour
  Pas de temps automatique
  Calcul cycles équivalents
  Capacité dynamique automatique
  Optimisation basée sur :
  Gain maximal
  Seuil % du gain max
  Percentile export journalier
  
  📊 Résultats fournis
  🔋 Batterie optimale (kWh / kW)
  💰 Gain annuel estimé
  📈 SOC agrégé (Journalier / Hebdo / Mensuel)
  📊 Import / Export avant optimisation
  📊 Import / Export après optimisation
  📉 Gain annuel vs Capacité
  🔁 Cycles équivalents annuels
  📥 Export Excel du fichier reconstitué

Dépendances principales :
  streamlit
  pandas
  numpy
  matplotlib
  fpdf
  xlsxwriter

📂 Format attendu des données
  Colonnes détectées automatiquement grâce aux mots-clés :
    Type	  --   Exemples détectés
    Date	  --   date, datetime, timestamp, horodatage
    Import  -- 	 soutirage, import, achat, réseau
    Export  -- 	 surplus, injection, réinjection
  
  Possibilité d’ajouter des mots-clés personnalisés dans la sidebar.

🧠 Logique d’optimisation
Calcul export journalier
Détermination capacité dynamique max

Boucle vectorisée sur :
  Capacités
  Puissances
  Simulation batterie complète
  Calcul gain réel HP/HC
  Sélection du plus petit couple (Capacité / Puissance)
  atteignant ≥ X% du gain maximal

🛠 Mode DEBUG
  Permet :
    Vérification dimensions vecteurs
    Vérification index temporel
    Validation cohérence calculs
    Analyse des anomalies

📈 Cas d’usage typiques
  Dimensionnement batterie photovoltaïque
  Analyse autoconsommation
  Comparaison scénarios tarifaires
  Étude rentabilité stockage
  Pré-dimensionnement avant devis installateur

🔒 Hypothèses du modèle
  Batterie idéale (pas de vieillissement)
  Rendement constant
  Pas de limitation réseau
  Décharge prioritaire sur import
  Charge prioritaire sur surplus export
