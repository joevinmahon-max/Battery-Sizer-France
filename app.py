import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime
from datetime import time
from fpdf import FPDF
from io import BytesIO
from zoneinfo import ZoneInfo  # gestion fuseaux horaires standard
import matplotlib.dates as mdates

# Fonction de gestion des dates
def remove_dst(dt_series):
    # Supprimer "DST"
    dt_series = dt_series.astype(str).str.replace(r'\sDST', '', regex=True)

    # Formats explicites (priorité Europe)
    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",

        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",

        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",

        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            result = pd.to_datetime(dt_series, format=fmt, errors='coerce')
            if result.notna().any():  # au moins une conversion réussie
                return result
        except:
            continue

    # Si aucun format ne fonctionne, laisse pandas deviner
    return pd.to_datetime(dt_series, errors='coerce')
    
# Date actuelle en GMT+1
now_gmt1 = datetime.datetime.now(ZoneInfo("Europe/Zurich"))

LongBase = 0

# ==========================================================
# PAGE CONFIG
# ==========================================================
st.set_page_config(page_title="Battery Sizer By JMN", layout="wide")
st.title("Battery Sizer - For France - By JMN")

# ==========================================================
# SIDEBAR PARAMETERS
# ==========================================================
dt_hours = 0.25

st.sidebar.header("📂 Type de données")
data_mode = st.sidebar.radio(
    "Format des données",
    ["Fichier EDF (mes-index-elec)"]
)

if data_mode == "Fichier EDF (mes-index-elec)":
    unite="kWh"
    st.sidebar.subheader("Options :")
    export_is_monthly = st.sidebar.checkbox("Export fourni en total mensuel (kWh/mois)", value=False)
    
    monthly_export_values = None         
    
    if export_is_monthly:
        st.sidebar.markdown("#### Saisir les 12 valeurs d'export (kWh)")
        months = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]
        monthly_export_values = {}
        for month in months:
            monthly_export_values[month] = st.sidebar.number_input(
                f"{month} (kWh)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )
        # Vérification qu'il y a bien 12 valeurs
        if len(monthly_export_values) != 12:
            st.error("❌ Les 12 mois doivent être renseignés.")
            st.stop()
        # Vérification qu'aucune valeur n'est vide ou nulle
        missing_months = [
            month for month, value in monthly_export_values.items()
            if value is None or value <= 0
        ]
        if missing_months:
            st.error(f"❌ Valeur manquante ou nulle pour : {', '.join(missing_months)}")
            st.stop()

values_are_kw = False

st.sidebar.subheader("🔎 Mots-clés personnalisés (optionnel)")
MotCle = st.sidebar.checkbox("Avec / Sans", value=False)
if MotCle:
    custom_date_tokens = st.sidebar.text_input(
        "Mots-clés Date (séparés par virgule)",
        value=""
    )
    custom_import_tokens = st.sidebar.text_input(
        "Mots-clés Import (séparés par virgule)",
        value=""
    )
    custom_export_tokens = st.sidebar.text_input(
        "Mots-clés Export (séparés par virgule)",
        value=""
    )
    
st.sidebar.header("💰 Paramètres des Tarifs GRD")
mode_tarif = st.sidebar.selectbox(
    "Type de tarification",
    ["Tarif unique", "Multi Tarifs"]
)

# ==============================
# MODE HP / HC
# ==============================
if mode_tarif == "Multi Tarifs":
    # -----------------------
    # Sélection GRD
    # -----------------------
    GRD = st.sidebar.selectbox(
        "Sélection du Tarif",
        [
            "Standard",
            "Tempo",
        ],
        key="GRD_select"
    )

    # -----------------------
    # Définition defaults
    # -----------------------
    default_hp = [(6, 22)]
    
    # ==============================
    # INITIALISATION & RESET PROPRE
    # ==============================

    if "tarif_state" not in st.session_state:
        st.session_state.tarif_state = {
            "active_GRD": GRD,
            "hp_ranges": default_hp.copy(),
            "nb_plages": len(default_hp),
        }

    state = st.session_state.tarif_state

    # Reset si GRD change
    if GRD != state["active_GRD"]:
        state["active_GRD"] = GRD
        state["hp_ranges"] = default_hp.copy()
        state["nb_plages"] = len(default_hp)
        # Suppression anciennes clés horaires
        for key in list(st.session_state.keys()):
            if key.startswith("hp_start_") or key.startswith("hp_end_"):
                del st.session_state[key]

    # ==============================
    # WEEK-END
    # ==============================
    st.sidebar.subheader("Plages horaires HP")

    # ==============================
    # NOMBRE DE PLAGES
    # ==============================
    state["nb_plages"] = st.sidebar.number_input(
        "Nombre de plages HP",
        min_value=1,
        max_value=5,
        value=state["nb_plages"]
    )

    # Synchronisation longueur
    while len(state["hp_ranges"]) < state["nb_plages"]:
        state["hp_ranges"].append((6, 22))

    while len(state["hp_ranges"]) > state["nb_plages"]:
        state["hp_ranges"].pop()

    # ==============================
    # ÉDITION DES PLAGES
    # ==============================
    
    hp_ranges = []

    for i in range(state["nb_plages"]):
    
        start_hour, end_hour = state["hp_ranges"][i]

        # Initialisation session_state si absent
        if f"hp_start_{i}" not in st.session_state:
            st.session_state[f"hp_start_{i}"] = time(start_hour, 0)
    
        if f"hp_end_{i}" not in st.session_state:
            st.session_state[f"hp_end_{i}"] = time(end_hour, 0)
    
        col1, col2 = st.sidebar.columns(2)
    
        with col1:
            start = st.selectbox(
                f"Début HP {i+1}",
                options=list(range(24)),
                index=start_hour,
                key=f"hp_start_{i}"
            )
    
        with col2:
            end = st.selectbox(
                f"Fin HP {i+1}",
                options=list(range(1, 25)),
                index=end_hour-1,
                key=f"hp_end_{i}"
            )
    
        state["hp_ranges"][i] = (start, end)
        hp_ranges.append((start, end))

    # -----------------------
    # TARIFS IMPORT
    # -----------------------
    st.sidebar.subheader("Import réseau")

    tariff_importHP = st.sidebar.number_input(
        "Tarif import HP (€/kWh)",
        min_value=0.0,
        value=0.32,
        step=0.01
    )

    tariff_importHC = st.sidebar.number_input(
        "Tarif import HC (€/kWh)",
        min_value=0.0,
        value=0.21,
        step=0.01
    )

    # -----------------------
    # TARIF EXPORT
    # -----------------------
    st.sidebar.subheader("Export réseau")

    tariff_export = st.sidebar.number_input(
        "Tarif export (€/kWh)",
        min_value=0.0,
        value=0.08,
        step=0.01
    )

# ==============================
# MODE TARIF UNIQUE
# ==============================
else:
    st.sidebar.subheader("Import / Export réseau")
    tariff_importHP = st.sidebar.number_input(
        "Tarif import (€/kWh)",
        min_value=0.0,
        value=0.32,
        step=0.01
    )

    tariff_importHC = tariff_importHP  # identique

    tariff_export = st.sidebar.number_input(
        "Tarif export (€/kWh)",
        min_value=0.0,
        value=0.08,
        step=0.01
    )

    hp_ranges = []  # pas utilisé

st.sidebar.header("⚙️ Paramètres")
debug = st.sidebar.checkbox("Avec / Sans DEBUG", value=False)
roundtrip_eff = st.sidebar.slider("Rendement aller-retour", 0.5, 1.0, 0.96)
cap_min = st.sidebar.number_input("Capacité min (kWh)", 1, 100, 5)
cap_max = st.sidebar.number_input("Capacité max (kWh)", 1, 200, 30)
cap_step = st.sidebar.number_input("Pas capacité (kWh)", 1, 20, 1)
soc_min_pct = st.sidebar.slider("SOC minimum batterie (%)", 0, 50, 5)
p_min = st.sidebar.number_input("Puissance min (kW)", 1, 50, 1)
p_max = st.sidebar.number_input("Puissance max (kW)", 1, 500, 10)
p_step = st.sidebar.number_input("Pas puissance (kW)", 1, 20, 1)
gain_threshold = st.sidebar.slider("Seuil % du gain max", 0.5, 1.0, 0.95)
daily_percentile = st.sidebar.slider("Percentile export journalier (Pxx)", 0.5, 0.99, 0.8)
st.sidebar.header("⚙️ Capacité Auto")
capacite_auto = st.sidebar.checkbox("Capacité auto dynamique", value=True)
if capacite_auto:
    facteur_auto = st.sidebar.slider("Facteur augmentation auto", 1.1, 3.0, 1.5)
    max_auto_extensions = st.sidebar.number_input("Nombre max d'auto-extensions", 1, 10, 5)
    cap_securite = st.sidebar.number_input("Capacité plafond sécurité (kWh)", 10, 10000, 10000)


def compute_gain_with_time_of_use(
    imp_array,
    exp_array,
    imp_after,
    exp_after,
    hours,
    weekdays
):
    import_avoided = imp_array - imp_after
    export_avoided = exp_array - exp_after

    is_hp = np.zeros(len(hours), dtype=bool)
    
    for start, end in hp_ranges:
        is_hp |= (hours >= start) & (hours < end)

    import_tariffs = np.where(is_hp, tariff_importHP, tariff_importHC)

    gain = np.sum(import_avoided * import_tariffs - export_avoided * tariff_export)

    return gain

def compute_import_export_cashflow(
    imp_array,
    exp_array,
    hours,
    weekdays
):
    """
    Calcule :
    - le coût total d'import
    - le revenu total d'export
    """

    # Détermination heures pleines
    is_hp = np.zeros(len(hours), dtype=bool)

    for start, end in hp_ranges:
        is_hp |= (hours >= start) & (hours < end)

    # Sélection du tarif import
    import_tariffs = np.where(is_hp, tariff_importHP, tariff_importHC)

    # Calculs
    import_cost = np.sum(imp_array * import_tariffs)
    export_revenue = np.sum(exp_array * tariff_export)

    return import_cost, export_revenue

# Fonction de détection ligne d'en-tête avec debug et expected_import_count
def find_header_row(df, date_tokens, import_tokens, expected_import_count=1, max_rows=120):
    """
    Cherche la ligne contenant au moins un token date et exactement `expected_import_count` tokens import.
    Affiche un debug ligne par ligne.
    Ignore les lignes trop courtes ou vides.
    """
    for r in range(min(max_rows, len(df))):
        row = df.iloc[r].astype(str).str.strip().tolist()
        if len(row) < 2:
            #st.write(f"Ligne {r} ignorée (trop courte ou vide) :", row)
            continue

        row_text = " | ".join(row)

        # Vérifie présence d'au moins un token date
        date_match = any(t.lower() in row_text.lower() for t in date_tokens)

        # Compte combien de tokens import sont présents (insensible à la casse)
        import_count = sum(1 for t in import_tokens if t.lower() in row_text.lower())

        # Debug complet
        #st.write(f"Ligne {r} :", row)
        #st.write(f" → texte concaténé : {row_text}")
        #st.write(f" → date_match={date_match}, import_count={import_count}/{expected_import_count}")


        if date_match and import_count == expected_import_count:
            st.success(f"Ligne d'en-tête détectée : {r}")
            return r

    st.error("❌ Aucune ligne d'en-tête trouvée")
    return None

# Fonction de détection collones
def find_columns(df, tokens, expected_count):
    found_cols = []
    used_columns = set()

    for col in df.columns:
        if col in used_columns:
            continue

        col_str = str(col).strip()

        for t in tokens:
            if t.lower() in col_str.lower():
                found_cols.append(col)
                used_columns.add(col)
                break

        if len(found_cols) == expected_count:
            break

    if len(found_cols) != expected_count:
        return None

    return found_cols

# Fonction de SIMULATION BATTERIE -- COEUR DU PROG
def simulate_battery(exp_array, imp_array, cap_kwh, power_kw, soc_min_pct, eta, dt_hours):
    soc_min_kWh = cap_kwh * soc_min_pct / 100
    soc_val = soc_min_kWh
    soc_list = []
    imp_after = np.zeros_like(imp_array)
    exp_after = np.zeros_like(exp_array)
    p_step_val = power_kw * dt_hours
    charge_series = np.zeros_like(exp_array)
    discharge_series = np.zeros_like(imp_array)

    eta_single = np.sqrt(eta)

    for i in range(len(exp_array)):
        # -----------------
        # CHARGE
        # -----------------
        max_charge = min(cap_kwh - soc_val, p_step_val)   # capacité restante limitée par puissance
        charge_i = min(exp_array[i], max_charge)          # on ne peut charger que ce qui est dispo
        energy_into_battery = charge_i * eta_single
        soc_val += energy_into_battery
        charge_series[i] = energy_into_battery          
        exp_after[i] = exp_array[i] - charge_i

        # -----------------
        # DÉCHARGE
        # -----------------     
        max_energy_from_battery = min(soc_val - soc_min_kWh, p_step_val / eta_single)     # énergie maximale qu’on peut retirer du SOC
        energy_from_battery = min(max_energy_from_battery, imp_array[i] / eta_single)     # énergie réellement retirée du SOC
        discharge_i = energy_from_battery * eta_single                                    # énergie fournie au bâtiment (après pertes)
        soc_val -= energy_from_battery
        discharge_series[i] = energy_from_battery
        imp_after[i] = imp_array[i] - discharge_i

        # -----------------
        # Bornage SOC pour sécurité
        # -----------------
        soc_val = min(max(soc_val, soc_min_kWh), cap_kwh)
        soc_list.append(soc_val)

    # Totaux annuels
    charge_total = np.sum(charge_series)
    discharge_total = np.sum(discharge_series)

    return soc_list, imp_after, exp_after, charge_series, discharge_series, charge_total, discharge_total

def eq_cycles_dod(charge_series, discharge_series, cap_kwh, soc_min_pct):
    soc_min = cap_kwh * soc_min_pct / 100
    soc_max = cap_kwh
    dod_series = (charge_series + discharge_series) / (soc_max - soc_min)
    eq_cycles = np.sum(dod_series) / 2
    return eq_cycles

# Choix du Type de fichier
if data_mode == "Fichier EDF (mes-index-elec)":
    uploaded_file = st.file_uploader(
    (
        "Choisir un fichier CSV -- \n"
        "Mots clefs :\n"
        "date [date, datetime, horodatage, timestamp, date/heure, date heure] -- \n"
        "import [soutirage, import, achat, reseau, consommation] -- \n"
        "export [surplus, surplus solaire, export, excedent, reinjection, réinjection, injection]"
    ),
    type=["csv"],
    accept_multiple_files=False
)
else:
    uploaded_file = st.file_uploader(
        "Choisir les 12 fichiers mensuels -- \n"
        "Mots clefs :\n"
        "date [début, date, datetime, horodatage, timestamp, date/heure, date heure] -- \n"
        "import [soutirage, import, achat, reseau, consommation] -- \n"
        "export [surplus, surplus solaire, export, excedent, reinjection, réinjection, injection]",
        type=["xlsx", "xls"],
        accept_multiple_files=True
    )
if uploaded_file:
    # ==========================================================
    # VERIFICATION PARAMETRES ENTREE
    # ==========================================================
    warnings = []
    if cap_min >= cap_max:
        warnings.append("⚠️ Capacité min >= capacité max.")
    if p_min >= p_max:
        warnings.append("⚠️ Puissance min >= puissance max.")
    if gain_threshold <= 0 or gain_threshold > 1:
        warnings.append("⚠️ Le seuil de gain doit être entre 0 et 1.")
    if roundtrip_eff <= 0 or roundtrip_eff > 1:
        warnings.append("⚠️ Le rendement doit être entre 0 et 1.")
    if dt_hours <= 0:
        warnings.append("⚠️ Le pas de temps doit être > 0.")
    if warnings:
        for w in warnings:
            st.error(w)
        st.stop()
    
    st.header("🔹 Recherche des lignes / collones")
    # ==========================================================
    # CAS 1 : FICHIER GRD
    # ==========================================================
    if data_mode == "Fichier EDF (mes-index-elec)":
        file_type = uploaded_file.name.split('.')[-1].lower()
        date_tokens = ["début", "date", "datetime", "horodatage", "timestamp", "date/heure", "date heure"]
        import_tokensBase = ["kWh"]
        import_tokensHPHC = ["Creuses", "Pleines"]
        import_tokensTempo = ["Creuses Bleu", "Pleines Bleu", "Creuses Blanc", "Pleines Blanc", "Creuses Rouge", "Pleines Rouge"]
        export_tokens = ["surplus", "surplus solaire", "export", "excedent", "reinjection", "réinjection", "positive", "injection"]

        # Ajouter mots-clés personnalisés si fournis
        if MotCle:
            if custom_date_tokens:
                date_tokens += [t.strip().lower() for t in custom_date_tokens.split(",")]
            
            if custom_import_tokens:
                import_tokens += [t.strip().lower() for t in custom_import_tokens.split(",")]
            
            if custom_export_tokens:
                export_tokens += [t.strip().lower() for t in custom_export_tokens.split(",")]

        if file_type == "csv":
            # Lire tout le fichier comme texte
            content = uploaded_file.read().decode("latin1")
            lines = [line for line in content.splitlines() if line.strip() != ""]  # supprime les lignes vides
            
            # Convertir en DataFrame
            df_full = pd.DataFrame([line.split(";") for line in lines])
            
            st.write("✅ Fichier converti - aperçu :")
            st.dataframe(df_full)

        # Choix des tokens import selon le tarif
        if mode_tarif == "Tarif unique":
            import_tokens = import_tokensBase
            expected_import_count = 1
        elif mode_tarif == "Multi Tarifs":
            if GRD == "Standard":
                import_tokens = import_tokensHPHC
                expected_import_count = 2
            elif GRD == "Tempo":
                import_tokens = import_tokensTempo
                expected_import_count = 6
        
        # Détection ligne d'en-tête
        header_row = find_header_row(df_full, date_tokens, import_tokens,expected_import_count)
        if header_row is None:
            st.error("❌ Impossible de détecter la ligne d'en-tête")
            st.stop()
            
        # ✅ Construire le vrai dataframe avec header correct
        header = df_full.iloc[header_row].tolist()
        data = df_full.iloc[header_row + 1:].reset_index(drop=True)
    
        df = pd.DataFrame(data.values, columns=header)
    
        st.success(f"Ligne d'en-tête détectée : {header_row}")
        st.write("✅ DataFrame final :")
        st.dataframe(df.head())
        
        # Réinitialiser l'état avant chaque fichier
        find_columns.used_columns = set()
        
        # Détection colonnes import
        imp_col = find_columns(df, import_tokens, expected_import_count)
        if imp_col is None:
            st.error(f"❌ Impossible de détecter exactement {expected_import_count} colonnes import")
            st.write("Colonnes disponibles :", list(df.columns))
            st.stop()
        else:
            st.success(f"Colonnes import détectées : {imp_col}")
        
        # Détection colonne date
        date_col = find_columns(df, date_tokens, expected_count=1)[0]
        st.success(f"Colonne date détectée : {date_col}")
        
        # Afficher lignes sans date
        missing_dates = df[df[date_col].isna()]
        if not missing_dates.empty:
            st.warning(f"⚠️ {len(missing_dates)} lignes n'ont pas de date et seront ignorées.")
            st.dataframe(missing_dates.head(10))

        # Supprimer uniquement les lignes sans date
        df = df.dropna(subset=[date_col]).reset_index(drop=True)

        st.header("🔹 Reconstruction journalière")

        # Nettoyage numérique (toutes les colonnes import)
        for col in imp_col:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        
        # Nettoyage date
        # certaines dates peuvent avoir DST
        df[date_col] = remove_dst(df[date_col])
        
        # Conversion en datetime
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce', utc=True)
        
        df[date_col] = df[date_col].dt.tz_convert(None)

        # Trier par date
        df = df.sort_values(date_col).reset_index(drop=True)

        # Calcul des deltas (différences)
        df_diff = df.copy()
        
        for col in imp_col:
            df_diff[col] = df[col].diff()
        
        # On supprime la première ligne (pas de delta)
        df_diff = df_diff.iloc[1:].reset_index(drop=True)
        
        # Extraire l'année
        df["year"] = df[date_col].dt.year
        
        # Compter le nombre de jours uniques par année
        year_counts = df.groupby("year")[date_col].nunique()
        
        # Définir plage acceptée (ici 360 à 366)
        min_days, max_days = 360, 366
        complete_years = year_counts[(year_counts >= min_days) & (year_counts <= max_days)].index.tolist()
        
        if not complete_years:
            st.error(f"❌ Aucune année complète détectée dans les données ({min_days}–{max_days} jours).")
            st.stop()
        
        # Si plusieurs années complètes → prendre la plus récente
        year = max(complete_years)
        st.success(f"✅ Année complète sélectionnée : {year}")
        
        # Filtrer uniquement cette année
        df = df[df["year"] == year].reset_index(drop=True)
        
        # DEBUG : vérifier la longueur du DataFrame final
        st.write(f"📊 Nombre de lignes après filtrage : {len(df)}")

        # Vérification : on attend 365 ou 366 lignes (1 par jour)
        if len(df) < 300:
            st.error("❌ Le fichier semble ne pas contenir des valeurs journalières complètes.")
            st.stop()
        
        # Création index annuel horaire
        date_range = pd.date_range(
            start=f"{year}-01-01 00:00:00",
            end=f"{year}-12-31 23:00:00",
            freq=f"{int(dt_hours*60)}min"
        )
        
        df_full = pd.DataFrame(index=date_range)
        df_full["date"] = df_full.index.date
        df_full["hour"] = df_full.index.hour
        df_full["import_kWh"] = 0.0
        df_full["export_kWh"] = 0.0

        if expected_import_count == 1:
            for _, row in df_diff.iterrows():
                day = row[date_col].date()
                total = row[imp_col[0]]
        
                if total <= 0:
                    continue
        
                mask = df_full["date"] == day
                steps = mask.sum()
        
                df_full.loc[mask, "import_kWh"] = total / steps
        
        elif expected_import_count == 2:
            hc_col = imp_col[0]
            hp_col = imp_col[1]
        
            for _, row in df_diff.iterrows():
                day = row[date_col].date()
        
                total_hc = row[hc_col]
                total_hp = row[hp_col]
        
                if total_hc <= 0 and total_hp <= 0:
                    continue
        
                mask_day = df_full["date"] == day
                mask_hc = mask_day & df_full["hour"].between(0, 5)
                mask_hp = mask_day & df_full["hour"].between(6, 21)
        
                if mask_hc.sum() > 0:
                    df_full.loc[mask_hc, "import_kWh"] = total_hc / mask_hc.sum()
        
                if mask_hp.sum() > 0:
                    df_full.loc[mask_hp, "import_kWh"] = total_hp / mask_hp.sum()
    
        elif expected_import_count == 6:
            for _, row in df_diff.iterrows():
                day = row[date_col].date()
        
                # On prend seulement les deltas positifs
                positive = {col: row[col] for col in imp_col if row[col] > 0}
        
                if len(positive) < 2:
                    continue
        
                hc_col = [c for c in positive if "creuses" in c.lower()][0]
                hp_col = [c for c in positive if "pleines" in c.lower()][0]
        
                total_hc = positive[hc_col]
                total_hp = positive[hp_col]
        
                mask_day = df_full["date"] == day
                mask_hc = mask_day & df_full["hour"].between(0, 5)
                mask_hp = mask_day & df_full["hour"].between(6, 21)
        
                if mask_hc.sum() > 0:
                    df_full.loc[mask_hc, "import_kWh"] = total_hc / mask_hc.sum()
        
                if mask_hp.sum() > 0:
                    df_full.loc[mask_hp, "import_kWh"] = total_hp / mask_hp.sum()
                
        df_full = df_full.reset_index().rename(columns={"index": date_col})
        df = df_full.sort_values(date_col).reset_index(drop=True)
        imp_col = "import_kWh"
        exp_col = "export_kWh"
        
        st.success("✅ Année reconstruite à partir des valeurs journalières.")
        st.write(f"📊 Nombre de lignes : {len(df)}")
        st.dataframe(df.head())

    if data_mode == "Fichier EDF (mes-index-elec)" and export_is_monthly :
        st.header(" 🔹 Nettoyage et conversion")
        st.info("⚙️ Reconstruction d’un profil export à partir des totaux mensuels.")
        # -----------------------------------------
        # Reconstruction export mensuel EXACT
        # -----------------------------------------

        month_map = {
            1: monthly_export_values["Janvier"],
            2: monthly_export_values["Février"],
            3: monthly_export_values["Mars"],
            4: monthly_export_values["Avril"],
            5: monthly_export_values["Mai"],
            6: monthly_export_values["Juin"],
            7: monthly_export_values["Juillet"],
            8: monthly_export_values["Août"],
            9: monthly_export_values["Septembre"],
            10: monthly_export_values["Octobre"],
            11: monthly_export_values["Novembre"],
            12: monthly_export_values["Décembre"],
        }

        df["month"] = df[date_col].dt.month
        df["hour"] = df[date_col].dt.hour

        # Production uniquement entre 10h et 16h
        df["solar_mask"] = df["hour"].between(10, 16)

        # Initialisation export
        df["export_kWh"] = 0.0

        for month in range(1, 13):
            mask_month = df["month"] == month
            mask_solar = mask_month & df["solar_mask"]

            total_hours = mask_solar.sum() * dt_hours  # nombre total d'heures solaires
            if total_hours > 0:
                export_per_hour = monthly_export_values[list(monthly_export_values.keys())[month-1]] / total_hours
                df.loc[mask_solar, "export_kWh"] = export_per_hour * dt_hours

        # Vérification des sommes mensuelles
        sums = df.groupby("month")["export_kWh"].sum()

        # Nettoyage colonnes temporaires
        df.drop(columns=["month", "hour", "solar_mask"], inplace=True)
    
    st.header(" 🔹 Nettoyage + verif global")
    # Calculer l'année majoritaire
    year_counts = df[date_col].dt.year.value_counts()
    target_year = year_counts.idxmax()  # l'année qui apparaît le plus
    
    # Filtrer le DataFrame pour ne garder que cette année
    df = df[df[date_col].dt.year == target_year].reset_index(drop=True)
    
    st.info(f"Filtrage pour l'année majoritaire : {target_year}")
        
    st.subheader("Aperçu du fichier reconstitué")
    st.write(f"Nombre de lignes : {len(df)}")
    LongApres = len(df)
    st.dataframe(df.head(10))  # Affiche les 10 premières lignes

    # =========================================
    # Vérification de la qualité des données
    # =========================================
   
    # Colonnes utilisées
    cols_needed = ["import_kWh", "export_kWh"]

     # 0 Vérifier nombre de lignes avant après
    if LongApres < LongBase*0.95 :
        st.error("❌ Nombre de lignes après conversion incohérent - Vérifier la syntaxe de la date")
        st.stop()

    # 1️ Vérifier qu'il n'y a pas de NaN
    nan_rows = df[df[cols_needed].isna().any(axis=1)]
    if not nan_rows.empty:
        st.error("⚠️ Certaines lignes contiennent des valeurs manquantes (NaN) :")
        st.dataframe(nan_rows)

    # 2️ Vérifier qu'il y a assez de données non nulles pour exploiter
    import_nonzero = (df["import_kWh"] > 0).sum()
    export_nonzero = (df["export_kWh"] > 0).sum()

    if import_nonzero == 0:
        st.error("❌ Toutes les valeurs d'import sont nulles. Impossible de simuler.")
        st.stop()
    if export_nonzero == 0:
        st.error("❌ Toutes les valeurs d'export sont nulles. Impossible de simuler.")
        st.info("Cocher dans la barre latérale « Export fourni en total mensuel » et entrer les valeurs manuellement.")
        st.stop()

    # 3️ Vérifier que les timestamps sont bien ordonnés
    if not df[date_col].is_monotonic_increasing:
        st.warning("⚠️ Les dates ne sont pas strictement croissantes, certaines anomalies sont possibles.")

   

    # 4 Vérifier qu'il y a un nombre minimal de points de données
    if len(df) < 1000:
        st.warning("⚠️ Le nombre total de lignes est très faible (<1000). La simulation risque d'être peu fiable.")

    # 5 Résumé des données
    import_total_before = df[imp_col].sum()
    export_total_before = df[exp_col].sum()
    import_total_after = df["import_kWh"].sum()
    export_total_after = df["export_kWh"].sum()
    
    import_nonzero = (df["import_kWh"] > 0).sum()
    export_nonzero = (df["export_kWh"] > 0).sum()
    
    st.info(
        f"📊 Résumé :\n"
        f"- Total de lignes : {len(df)}\n"
        f"- Import non nul : {import_nonzero} lignes\n"
        f"- Export non nul : {export_nonzero} lignes\n"
        f"- Valeurs min/max import : {df['import_kWh'].min():.2f} / {df['import_kWh'].max():.2f}\n"
        f"- Valeurs min/max export : {df['export_kWh'].min():.2f} / {df['export_kWh'].max():.2f}\n"
        f"- Total import avant conversion : {import_total_before:.2f} \n"
        f"- Total import après conversion : {import_total_after:.2f} \n"
        f"- Total export avant conversion : {export_total_before:.2f} \n"
        f"- Total export après conversion : {export_total_after:.2f} "
    )

    st.info("📥 Télécharger le fichier Excel reconstitue")

    # Créer un buffer Excel
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Reconstitue")
    excel_buffer.seek(0)
    
    # Repositionner le curseur au début du buffer
    excel_buffer.seek(0)
    
    # Bouton Streamlit pour télécharger le fichier
    st.download_button(
        label="Télécharger le fichier Excel reconstitué",
        data=excel_buffer,
        file_name="fichier_reconstitue.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.header(" 🔹 SIMULATION VECTORISÉE")
    # ==========================================================
    # CALCUL CAPACITÉ MAX DYNAMIQUE (avec auto-extension + auto-step)
    # ==========================================================
    with st.spinner("Calcul de la capacité maximale dynamique..."):

        daily_export = df.groupby(df[date_col].dt.date)["export_kWh"].sum()
        cap_dyn_raw = np.ceil(np.percentile(daily_export, daily_percentile*100))

        auto_extension_count = 0
        original_cap_max = cap_max
        original_cap_step = cap_step

        # Vérifie plafonnement
        if cap_dyn_raw >= cap_max:

            if capacite_auto:
                old_cap = cap_max

                while cap_dyn_raw >= cap_max and auto_extension_count < max_auto_extensions:
                    cap_max = min(int(cap_max * facteur_auto), cap_securite)
                    auto_extension_count += 1

                st.info(
                    f"⚙️ Capacité dynamique dépassait la limite. "
                    f"cap_max ajusté automatiquement de {old_cap} à {cap_max} kWh "
                    f"({auto_extension_count} extension(s))."
                )

                if cap_max == cap_securite:
                    st.error("⚠️ Plafond (cap_securite) atteint.")
                if auto_extension_count == max_auto_extensions:
                    st.error("⚠️ Plafond (max_auto_extensions) atteint.")

                # ==================================================
                # AJUSTEMENT AUTOMATIQUE DU PAS DE CAPACITÉ
                # ==================================================
                target_points = 40  # nombre max de capacités testées
                range_size = cap_max - cap_min

                if range_size > target_points:
                    cap_step = max(1, int(np.ceil(range_size / target_points)))
                    st.info(
                        f"⚙️ cap_step ajusté automatiquement de "
                        f"{original_cap_step} à {cap_step} kWh "
                        f"pour limiter le temps de calcul."
                    )
            else:
                st.warning(
                    "⚠️ Capacité dynamique plafonnée par cap_max → "
                    "Activer 'Capacité auto dynamique' ou augmenter cap_max."
                )
        cap_max_dyn = min(max(cap_dyn_raw, cap_min), cap_max)

        st.sidebar.markdown(f" Capacité max dynamique: **{cap_max_dyn} kWh**")
    
    # ==========================================================
    # SIMULATION VECTORISÉE
    # ==========================================================  
    timestamps = pd.to_datetime(df[date_col])
    hours = timestamps.dt.hour.to_numpy(dtype=int)
    weekdays = timestamps.dt.weekday.to_numpy(dtype=int)

    exp_array = df["export_kWh"].values
    imp_array = df["import_kWh"].values

    import_cost, export_revenue = compute_import_export_cashflow(
        imp_array,
        exp_array,
        hours,
        weekdays
    )
    
    #st.write(f"Coût total import : {import_cost:.2f} €")
    #st.write(f"Revenu total export : {export_revenue:.2f} €")
        
    with st.spinner("Simulation et recherche du meilleur choix..."):
        exp_array = df["export_kWh"].values
        imp_array = df["import_kWh"].values
        eta = np.sqrt(roundtrip_eff)

        caps = np.arange(cap_min, cap_max_dyn+1, cap_step)
        powers = np.arange(p_min, p_max+1, p_step)
        results = []

        for cap in caps:
            for p in powers:
                soc_min_kWh = cap * soc_min_pct / 100

                p_step_val = p * dt_hours
                soc = np.zeros_like(exp_array)
                soc_val = 0
                exp_after = np.zeros_like(exp_array)
                imp_after = np.zeros_like(exp_array)

                charge = np.minimum(exp_array, p_step_val)
                discharge = np.minimum(imp_array, p_step_val)

                soc_list_tmp, imp_after_tmp, exp_after_tmp, charge_series_tmp, discharge_series_tmp, charge_total_tmp, discharge_total_tmp = simulate_battery(
                exp_array, imp_array, cap, p, soc_min_pct, eta, dt_hours)
            
                gain = compute_gain_with_time_of_use(
                imp_array,
                exp_array,
                imp_after_tmp,
                exp_after_tmp,
                hours,
                weekdays
                )

                eq_cycles = eq_cycles_dod(charge_series_tmp, discharge_series_tmp, cap, soc_min_pct)

                results.append([cap, p, gain, eq_cycles])

        results_df = pd.DataFrame(results, columns=["Cap_kWh","Power_kW","Gain_Euro","Cycles"])
        gain_max = results_df["Gain_Euro"].max()
        threshold = gain_threshold * gain_max
        candidates = results_df[results_df["Gain_Euro"] >= threshold]
        best = candidates.sort_values(["Cap_kWh","Power_kW"], ignore_index=True).iloc[0]

    st.success(f"🔋 Batterie optimale : {best.Cap_kWh} kWh / {best.Power_kW} kW")
    st.success(f"Gain annuel: {round(best.Gain_Euro,2)} €")

    # ===========================
    # Résumé de la batterie réelle
    # ===========================
    soc_list, imp_after, exp_after, charge_series, discharge_series, charge_total, discharge_total = simulate_battery(
    exp_array, imp_array, best.Cap_kWh, best.Power_kW, soc_min_pct, eta, dt_hours)

    soc_min_real = min(soc_list)
    soc_max_real = max(soc_list)
    charge_total_real = charge_total
    discharge_total_real = discharge_total

    st.subheader("Résumé réel de la batterie")
    st.write(f"- SOC minimum atteint : {soc_min_real:.2f} kWh ({soc_min_real/best.Cap_kWh*100:.1f}%)")
    st.write(f"- SOC maximum atteint : {soc_max_real:.2f} kWh ({soc_max_real/best.Cap_kWh*100:.1f}%)")
    st.write(f"- Energie totale chargée : {charge_total_real:.2f} kWh")
    st.write(f"- Energie totale déchargée : {discharge_total_real:.2f} kWh")

    # Vérification gain réel

    gain_real = compute_gain_with_time_of_use(
    imp_array,
    exp_array,
    imp_after,
    exp_after,
    hours,
    weekdays
    )
    st.write(f"- Verification Gain réel simulation : {gain_real:.2f} €")

    # ==========================================================
    # SOC VECTORISÉ
    # ==========================================================

    soc_list, imp_after, exp_after, charge_series, discharge_series, charge_total, discharge_total = simulate_battery(
    exp_array, imp_array, best.Cap_kWh, best.Power_kW, soc_min_pct, eta, dt_hours)
    df["SOC_pct"] = [(s / best.Cap_kWh)*100 for s in soc_list]

    # ==========================================================
    # PRÉPARATION DES DONNÉES
    # ==========================================================
    df = df.sort_values(by=date_col)
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)

    # Nettoyage
    df["import_kWh"] = df["import_kWh"].clip(lower=0).fillna(0)
    df["export_kWh"] = df["export_kWh"].clip(lower=0).fillna(0)

    imp_after = pd.Series(imp_after, index=df.index).clip(lower=0).fillna(0)
    exp_after = pd.Series(exp_after, index=df.index).clip(lower=0).fillna(0)

    st.header(" 🔹 Graphiques")
    
    # ==========================================================
    # CHOIX AGRÉGATION
    # ==========================================================
    aggregation_choice = st.selectbox(
        "📅 Niveau d'agrégation",
        ["Journalier", "Hebdomadaire", "Mensuel"],
        index=2
    )
    freq_map = {
        "Journalier": "D",
        "Hebdomadaire": "W",
        "Mensuel": "M"
    }
    freq = freq_map[aggregation_choice]

    # ==========================================================
    # AGRÉGATION
    # ==========================================================
    # Avant optimisation : SOC en %
    before_agg = df[["import_kWh", "export_kWh", "SOC_pct"]].copy()
    before_agg = before_agg.resample(freq).agg({
        "import_kWh": "sum",
        "export_kWh": "sum",
        "SOC_pct": "mean" 
    })

    # Après optimisation : SOC en %
    after_agg = pd.DataFrame({
        "import_after": imp_after,
        "export_after": exp_after,
        "SOC_pct": df["SOC_pct"]  # SOC déjà en %
    }, index=df.index)
    after_agg = after_agg.resample(freq).agg({
        "import_after": "sum",
        "export_after": "sum",
        "SOC_pct": "mean"
    })

    # Détecter l'année automatiquement
    year_min = before_agg.index.min().year
    year_max = before_agg.index.max().year
    
    # ==========================================================
    # GRAPHIQUE SOC MATPLOTLIB 
    # ==========================================================
    st.subheader("📈 SOC (%) - Agrégation")
    fig_soc, ax_soc = plt.subplots(figsize=(12,5))
    
    ax_soc.plot(after_agg.index, after_agg["SOC_pct"], label="SOC après (%)", color='blue')
    
    ax_soc.set_xlabel("Mois")
    ax_soc.set_ylabel("SOC (%)")
    ax_soc.set_title("État de charge batterie")
    ax_soc.set_ylim(0, 100)  # échelle SOC fixe 0-100%    
    ax_soc.legend()
    ax_soc.grid(alpha=0.3)

    # Limiter à l'année complète automatiquement
    ax_soc.set_xlim(pd.Timestamp(f"{year_min}-01-01"), pd.Timestamp(f"{year_max}-12-31"))

    # Tick par mois
    ax_soc.xaxis.set_major_locator(mdates.MonthLocator())
    ax_soc.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    
    fig_soc.autofmt_xdate()
    st.pyplot(fig_soc)

    # Calcul de l'échelle commune
    max_import_export = max(
        before_agg[["import_kWh","export_kWh"]].max().max(),
        after_agg[["import_after","export_after"]].max().max()
    )

    # ===========================
    # Graphique AVANT
    # ===========================
    st.subheader("📊 Import / Export AVANT optimisation")
    fig_before, ax_before = plt.subplots(figsize=(12,5))

    ax_before.plot(before_agg.index, before_agg["import_kWh"], label="Import avant (kWh)")
    ax_before.plot(before_agg.index, before_agg["export_kWh"], label="Export avant (kWh)")

    ax_before.set_ylabel("Énergie (kWh)")
    ax_before.set_xlabel("Mois")
    ax_before.set_title("Import / Export AVANT optimisation")
    ax_before.set_ylim(0, max_import_export*1.05)
    ax_before.legend()
    ax_before.grid(alpha=0.3)

    # Limiter à l'année complète automatiquement
    ax_before.set_xlim(pd.Timestamp(f"{year_min}-01-01"), pd.Timestamp(f"{year_max}-12-31"))

    # Tick par mois
    ax_before.xaxis.set_major_locator(mdates.MonthLocator())
    ax_before.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    fig_before.autofmt_xdate()
    st.pyplot(fig_before)

    # ===========================
    # Graphique APRÈS
    # ===========================
    st.subheader("📊 Import / Export APRÈS optimisation")
    fig_after, ax_after = plt.subplots(figsize=(12,5))

    ax_after.plot(after_agg.index, after_agg["import_after"], label="Import après (kWh)")
    ax_after.plot(after_agg.index, after_agg["export_after"], label="Export après (kWh)")

    ax_after.set_ylabel("Énergie (kWh)")
    ax_after.set_xlabel("Mois")
    ax_after.set_title("Import / Export APRÈS optimisation")
    ax_after.set_ylim(0, max_import_export*1.05)
    ax_after.legend()
    ax_after.grid(alpha=0.3)

    # Limiter à l'année complète automatiquement
    ax_after.set_xlim(pd.Timestamp(f"{year_min}-01-01"), pd.Timestamp(f"{year_max}-12-31"))

    # Tick par mois
    ax_after.xaxis.set_major_locator(mdates.MonthLocator())
    ax_after.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    fig_after.autofmt_xdate()
    st.pyplot(fig_after)

    # ==========================================================
    # Courbe du gain annuel en fonction de la capacité
    # ==========================================================
    st.subheader("📊 Gain annuel vs Capacité batterie")

    # On moyenne le gain sur toutes les puissances pour chaque capacité
    gain_by_cap = results_df.groupby("Cap_kWh")["Gain_Euro"].max()  # ou .mean() si tu veux moyenne

    fig_gain, ax_gain = plt.subplots(figsize=(10,5))
    ax_gain.plot(gain_by_cap.index, gain_by_cap.values, marker='o', color='green')
    ax_gain.set_xlabel("Capacité batterie (kWh)")
    ax_gain.set_ylabel("Gain annuel (€)")
    ax_gain.set_title("Gain annuel en fonction de la capacité de la batterie")
    ax_gain.grid(alpha=0.3)

    # Affiche la figure dans Streamlit
    st.pyplot(fig_gain)

    # ==========================================================
    # CALCULS POUR LE RAPPORT
    # ==========================================================
    # Import/Export avant
    import_before = df["import_kWh"].sum()
    export_before = df["export_kWh"].sum()

    # Simulation SOC pour batterie optimale
    soc_list, imp_after, exp_after, charge_series, discharge_series, charge_total, discharge_total = simulate_battery(
    exp_array, imp_array, best.Cap_kWh, best.Power_kW, soc_min_pct, eta, dt_hours)

    df["SOC"] = soc_list

    # Calcul gains
    gain_net = compute_gain_with_time_of_use(
    imp_array,
    exp_array,
    imp_after,
    exp_after,
    hours,
    weekdays
    )
    
    eq_cycles = (charge_total + discharge_total) / (2 * best.Cap_kWh)

    if debug :
        # ==========================================================
        # VERIFICATION RESULTATS
        # ==========================================================
        st.header("🛠 DEBUG & VALIDATION DES DONNÉES")
        # ==========================================================
        # 1️ Vérification tailles des vecteurs
        # ==========================================================
        st.subheader("1️ Vérification dimensions")
        
        st.write("Longueur df :", len(df))
        st.write("Longueur imp_array :", len(imp_array))
        st.write("Longueur exp_array :", len(exp_array))
        st.write("Longueur imp_after :", len(imp_after))
        st.write("Longueur exp_after :", len(exp_after))
        st.write("Longueur soc_list :", len(soc_list))
        
        if not (
            len(df) == len(imp_array) == len(exp_array) == len(imp_after) == len(exp_after) == len(soc_list)
        ):
            st.error("❌ ERREUR : Les vecteurs n'ont pas la même longueur !")
        else:
            st.success("✅ Toutes les longueurs correspondent")
        
        # ==========================================================
        # 2️ Vérification index datetime
        # ==========================================================
        st.subheader("2️ Vérification index temporel")
        
        if not isinstance(df.index, pd.DatetimeIndex):
            st.error("❌ df n'a pas un DatetimeIndex")
        else:
            st.success("✅ df a un DatetimeIndex")
        
        if not df.index.is_monotonic_increasing:
            st.error("❌ Les dates ne sont pas triées")
        else:
            st.success("✅ Les dates sont triées")
        
        if df.index.has_duplicates:
            st.error("❌ Il y a des dates en doublon")
            duplicates = df[df.index.duplicated(keep=False)]
            st.write("Nombre doublons :", len(duplicates))
            st.dataframe(duplicates.head(1000))
        else:
            st.success("✅ Pas de doublons temporels")
        
        # ==========================================================
        # 3️ Vérification cohérence énergie AVANT / APRÈS
        # ==========================================================
        st.subheader("3️ Vérification énergie")
        
        import_before = df["import_kWh"].sum()
        export_before = df["export_kWh"].sum()
        
        import_after_total = imp_after.sum()
        export_after_total = exp_after.sum()
        
        st.write("Import total AVANT :", import_before)
        st.write("Import total APRÈS :", import_after_total)
        st.write("Export total AVANT :", export_before)
        st.write("Export total APRÈS :", export_after_total)
        
        if import_after_total > import_before + 1e-6:
            st.error("❌ Import après > import avant (impossible)")
        else:
            st.success("✅ Import cohérent")
        
        # ==========================================================
        # 4️ Vérification conservation énergétique batterie
        # ==========================================================
        st.subheader("4️ Vérification conservation énergie batterie")
        
        energy_delta_soc = soc_list[-1] - soc_list[0]
        battery_balance = charge_total - discharge_total
        
        st.write("ΔSOC total (kWh) :", energy_delta_soc)
        st.write("Charge - Décharge :", battery_balance)
        
        if abs(energy_delta_soc - battery_balance) > 0.01:
            st.error("❌ Incohérence dans le bilan batterie")
        else:
            st.success("✅ Bilan batterie cohérent")
        
        # ==========================================================
        # 5️ Vérification SOC
        # ==========================================================
        st.subheader("5️ Vérification SOC")
        
        soc_min = min(soc_list)
        soc_max = max(soc_list)
        
        st.write("SOC min (kWh) :", soc_min)
        st.write("SOC max (kWh) :", soc_max)
    
        st.write("Somme charge_series :", charge_series.sum())
        st.write("Somme discharge_series :", discharge_series.sum())
    
        st.write("charge_total :", charge_total)
        st.write("discharge_total :", discharge_total)
    
        # ==========================================================
        # DEBUG CONSERVATION ÉNERGIE BATTERIE
        # ==========================================================
        
        delta_soc = soc_list[-1] - soc_list[0]
        energy_balance = np.sum(charge_series) - np.sum(discharge_series)
        difference = delta_soc - energy_balance
        
        st.subheader("🔍 Debug conservation batterie")
        
        st.write(f"ΔSOC (kWh) : {delta_soc:.6f}")
        st.write(f"Somme(charge_series) - Somme(discharge_series) : {energy_balance:.6f}")
        st.write(f"Différence : {difference:.10f}")
        
        tolerance = 1e-6
        
        if abs(difference) < tolerance:
            st.success("✅ Conservation énergétique OK")
        else:
            st.error("❌ Problème de cohérence énergétique")
        
        if soc_min < 0:
            st.error("❌ SOC négatif")
        if soc_max > best.Cap_kWh + 1e-6:
            st.error("❌ SOC dépasse capacité batterie")
        else:
            st.success("✅ SOC dans les limites physiques")
        
        # ==========================================================
        # 6️ Vérification agrégation
        # ==========================================================
        st.subheader("6️ Vérification agrégation")
        
        sum_before_agg = before_agg["import_kWh"].sum()
        sum_after_agg = after_agg["import_after"].sum()
        
        st.write("Somme import AVANT (agrégé) :", sum_before_agg)
        st.write("Somme import APRÈS (agrégé) :", sum_after_agg)
        
        if abs(sum_before_agg - import_before) > 0.01:
            st.error("❌ Agrégation AVANT incorrecte")
        else:
            st.success("✅ Agrégation AVANT correcte")
        
        if abs(sum_after_agg - import_after_total) > 0.01:
            st.error("❌ Agrégation APRÈS incorrecte")
        else:
            st.success("✅ Agrégation APRÈS correcte")
        
        # ==========================================================
        # 7️ Vérification valeurs négatives
        # ==========================================================
        st.subheader("7️ Vérification valeurs négatives")
        
        if (imp_after < 0).any():
            st.error("❌ Valeurs négatives dans imp_after")
        
        if (exp_after < 0).any():
            st.error("❌ Valeurs négatives dans exp_after")
        
        if (df["import_kWh"] < 0).any():
            st.error("❌ Valeurs négatives dans import_kWh")
        
        if (df["export_kWh"] < 0).any():
            st.error("❌ Valeurs négatives dans export_kWh")
        
        st.success("✅ Aucune valeur négative détectée")

        st.subheader("🔍 DEBUG TARIFICATION Multi Tarifs")

        # Reconstruction masque HP
        is_hp = np.zeros(len(hours), dtype=bool)
    
        for start, end in hp_ranges:
            is_hp |= (hours >= start) & (hours < end)
    
        hp_count = np.sum(is_hp)
        hc_count = len(is_hp) - hp_count
    
        st.write("Nombre total points :", len(hours))
        st.write("HP count :", hp_count)
        st.write("HC count :", hc_count)
    
        if hp_count == 0:
            st.error("❌ AUCUNE heure HP détectée → problème plage horaire")

        
        st.subheader("🔍 Distribution des heures")
        unique_hours = np.unique(hours)
        st.write("Heures présentes :", unique_hours)

        st.subheader("🔍 Test sensibilité tarif")
    
        test_gain_hp_plus = np.sum((imp_array - imp_after) * (tariff_importHP + 0.05))
        st.write("Gain si HP + 0.05 € :", test_gain_hp_plus)

    
        st.subheader("🔍 Test FULL HP")
    
        gain_full_hp = np.sum((imp_array - imp_after) * tariff_importHP - 
                              (exp_array - exp_after) * tariff_export)
    
        st.write("Gain si 100% HP :", gain_full_hp)
        
        st.success("🎯 DEBUG TERMINÉ")

    st.header(" 🔹 Alertes")
    alerts = []

    # SOC limites physiques
    soc_max = np.max(df["SOC_pct"])
    soc_min = np.min(df["SOC_pct"])

    if soc_max > 100.1:
        alerts.append(f"⚠️ SOC dépasse 100% (max = {soc_max:.2f}%).")

    if soc_min < soc_min_pct - 0.1:
        alerts.append(f"⚠️ SOC descend sous 0% (min = {soc_min:.2f}%).")

    # Gain négatif
    if gain_net < 0:
        alerts.append("⚠️ Le gain net est négatif → batterie non rentable.")

    # Cycles excessifs (ex : > 365/an)
    if eq_cycles > 365:
        alerts.append(f"⚠️ Cycles élevés ({eq_cycles:.1f}/an) → usure importante.")

    # Batterie optimale en limite de plage
    if best.Cap_kWh == cap_min or best.Cap_kWh == cap_max:
        alerts.append("⚠️ Capacité optimale en limite de plage → élargir intervalle.")

    if (best.Power_kW == p_min) or (best.Power_kW == p_max):
        alerts.append("⚠️ Puissance optimale en limite de plage → élargir intervalle.")

    # Capacité dynamique bloquée par cap_max
    #if cap_max_dyn == cap_max:
        #alerts.append("⚠️ Capacité dynamique plafonnée par cap_max → augmenter cap_max pour analyse complète.")

    # Affichage alertes
    if alerts:
        st.warning(" ⚠️ Alertes de vérification")
        for a in alerts:
            st.write(a)
    else:
        st.success("✅ Vérification résultats : aucune anomalie détectée.")
    
    st.header(" 🔹 Export PDF Client")
    # ==========================================================
    # EXPORT PDF CLIENT PROFESSIONNEL
    # ==========================================================
    
    import_avoided = (imp_array - imp_after).sum()
    export_avoided = (exp_array - exp_after).sum()
    
    with st.spinner("Génération PDF client…"):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # -------------------------
        # PAGE 1 : Couverture
        # -------------------------
        if data_mode == "Fichier EDF (mes-index-elec)":
            file_info = uploaded_file.name
        else:
            names = "\n".join([f.name for f in uploaded_file])
            file_info = names

        pdf.add_page()
        pdf.set_font("Arial", 'B', 18)
        pdf.cell(0, 10, "Simulation Batterie Optimisée", ln=True, align="C")
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 8, "Version : V0 - 03.03.2026 - JMN", ln=True)
        pdf.ln(8)
        pdf.set_font("Arial", '', 12)
        pdf.multi_cell(0, 8,
        f"Date : {now_gmt1.strftime('%d/%m/%Y %H:%M')}\n"
        f"Projet : Simulation client\n"
        f"Résumé : Capacité et puissance optimales, gain estimé et alertes éventuelles\n"
        f"Fichier de données : {file_info}")
        pdf.ln(5)

        # -------------------------
        # AJOUT INFO EXPORT MENSUEL
        # -------------------------
        if data_mode == "Fichier EDF (mes-index-elec)" and export_is_monthly :
            pdf.set_font("Arial", 'I', 12)
            pdf.multi_cell(0, 8,
                "Profil export reconstitué à partir des totaux mensuels.")
            pdf.ln(5)

            # Liste des mois et valeurs export
            pdf.set_font("Arial", '', 12)
            pdf.multi_cell(0, 8, "Valeurs mensuelles (kWh) :", ln=True)
            for month in ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                          "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]:
                value = monthly_export_values.get(month, 0)
                pdf.cell(0, 6, f"{month} : {value:.1f} kWh", ln=True)
            pdf.ln(5)

        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Paramètres de simulation - Non Commercial", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", '', 10)

        # -----------------------
        # TARIFS :     tariff_importHP, tariff_importHC, tariff_export
        # HORAIRES :   hp_ranges.append((start, end))
        # -----------------------
        # Transformation des plages horaires en texte
        if hp_ranges:  # s'il y a des plages HP définies
            hp_ranges_str = ", ".join([f"{start:02d}h-{end:02d}h" for start, end in hp_ranges])
        else:
            hp_ranges_str = "N/A"
            
        param_table = [
            ["Pas de temps (h)", dt_hours],
            ["Reconstruction du profil annuel Export par totaux mensuels.", export_is_monthly],
            ["Unité des valeurs", unite],
            ["Rendement aller-retour", roundtrip_eff],
            ["SOC min (%)", soc_min_pct],
            ["Capacité min (kWh)", cap_min],
            ["Capacité max (kWh)", cap_max],
            ["Pas capacité (kWh)", cap_step],
            ["Puissance min (kW)", p_min],
            ["Puissance max (kW)", p_max],
            ["Pas puissance (kW)", p_step],
            ["Tarif import HP (Euros/kWh)", tariff_importHP],
            ["Tarif import HC (Euros/kWh)", tariff_importHC],
            ["Tarif export (Euros/kWh)", tariff_export],
            ["Plages horaires HP", hp_ranges_str],
            ["Percentile export journalier", daily_percentile]
        ]

        # Dessiner tableau
        for row in param_table:
            pdf.cell(120, 6, str(row[0]), border=1)
            pdf.cell(40, 6, str(row[1]), border=1, ln=True)

        # -------------------------
        # PAGE 2 : 
        # -------------------------
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Résultats annuels estimés - Non Commercial", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", '', 10)

        results_table = [
            ["Capacité optimale (kWh)", best.Cap_kWh],
            ["Puissance optimale (kW)", best.Power_kW],
            ["Gain annuel net (Euros)", round(gain_net, 2)],
            ["Gain maximum (Euros)", round(gain_max, 2)],
            ["Seuil choisi (%)", gain_threshold*100],
            ["Cycles équivalents/an", round(eq_cycles, 2)],
            ["SOC min réel (%)", round(soc_min_real/best.Cap_kWh*100, 1)],
            ["SOC max réel (%)", round(soc_max_real/best.Cap_kWh*100, 1)],
            ["Énergie totale chargée (kWh)", round(charge_total_real, 2)],
            ["Énergie totale déchargée (kWh)", round(discharge_total_real, 2)],
            ["Import avant (kWh)", round(import_before, 2)],
            ["Import après (kWh)", round(imp_after.sum(), 2)],
            ["Export avant (kWh)", round(export_before, 2)],
            ["Export après (kWh)", round(exp_after.sum(), 2)],
            ["Import évité (kWh)", round(import_avoided, 2)],
            ["Export évité (kWh)", round(export_avoided, 2)],
            ["Capacité max dynamique (kWh)", cap_max_dyn]
        ]
        for row in results_table:
            pdf.cell(120, 6, str(row[0]), border=1)
            pdf.cell(40, 6, str(row[1]), border=1, ln=True)
        
        pdf.ln(5)
        # Courbe du gain annuel en fonction de la capacité
        img_gainAnn = BytesIO()
        fig_gain.savefig(img_gainAnn, format="png")
        img_gainAnn.seek(0)
        pdf.image(img_gainAnn, x=15, w=180)


        # -------------------------
        # PAGE 4 : Résultats annuels - COMMERCIAL
        # -------------------------
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Paramètres de simulation", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", '', 10)

        param_table = [
            ["Rendement aller-retour", roundtrip_eff],
            ["SOC min (%)", soc_min_pct],
            ["Capacité min (kWh)", cap_min],
            ["Capacité max (kWh)", cap_max],
            ["Puissance min (kW)", p_min],
            ["Puissance max (kW)", p_max],
            ["Tarif import HP (Euros/kWh)", tariff_importHP],
            ["Tarif import HC (Euros/kWh)", tariff_importHC],
            ["Tarif export (Euros/kWh)", tariff_export],
            ["Plages horaires HP", hp_ranges_str],
        ]
        # Dessiner tableau
        for row in param_table:
            pdf.cell(120, 6, str(row[0]), border=1)
            pdf.cell(40, 6, str(row[1]), border=1, ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Résultats annuels estimés", ln=True)
        pdf.set_font("Arial", '', 10)
        pdf.ln(5)
        results_table = [
            ["Capacité optimale (kWh)", best.Cap_kWh],
            ["Puissance optimale (kW)", best.Power_kW],
            ["Seuil choisi (%)", gain_threshold*100],
            ["Cycles équivalents/an", round(eq_cycles, 2)],
            ["Import avant (kWh)", round(import_before, 2)],
            ["Import après (kWh)", round(imp_after.sum(), 2)],
            ["Export avant (kWh)", round(export_before, 2)],
            ["Export après (kWh)", round(exp_after.sum(), 2)],
            ["Import évité (kWh)", round(import_avoided, 2)],
            ["Export évité (kWh)", round(export_avoided, 2)],
        ]
        # Dessiner tableau
        for row in results_table:
            pdf.cell(120, 6, str(row[0]), border=1)
            pdf.cell(40, 6, str(row[1]), border=1, ln=True)

        # =========================
        # GLOSSAIRE / DEFINITIONS
        # =========================
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "Glossaire / Définitions", ln=True)
        pdf.ln(5)

        definitions = {
            "SOC (%)": "State of Charge - niveau de charge de la batterie en pourcentage de sa capacité totale.",
            "Capacité (kWh)": "Quantité maximale d'énergie que la batterie peut stocker.",
            "Puissance (kW)": "Vitesse maximale à laquelle la batterie peut charger ou décharger.",
            "Cycles équivalents": "Nombre de cycles complets de charge/décharge que la batterie réalise sur l'année.",
            "Import/Export (kWh)": "Énergie achetée (import) ou revendue (export) au réseau électrique.",
            "Rendement aller-retour": "Pourcentage de l'énergie restituée par la batterie après chargement et déchargement.",
            "Seuil choisi en % du gain max": "Pourcentage du gain maximal utilisé pour sélectionner la capacité et puissance optimales.",
        }

        pdf.set_font("Arial", '', 10)
        cell_width = 180  # largeur utile

        for term, definition in definitions.items():
            # terme en gras au début de la ligne, suivi de la définition en texte normal
            text = f"{term}: {definition}"
            pdf.set_font("Arial", '', 8)
            pdf.multi_cell(cell_width, 6, text)
            pdf.ln(2)  # espace entre définitions

        # -------------------------
        # PAGE 4 : Graphiques
        # -------------------------
        # Graph SOC
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 8, "Graphiques", ln=True)
        pdf.ln(2)

        # -------------------------
        # Graph SOC
        # -------------------------
        img_buf_soc = BytesIO()
        fig_soc.savefig(img_buf_soc, format="png")
        img_buf_soc.seek(0)
        pdf.image(img_buf_soc, x=15, w=180)
        pdf.ln(2)

        # Import / Export avant
        img_buf_before = BytesIO()
        fig_before.savefig(img_buf_before, format="png")
        img_buf_before.seek(0)
        pdf.image(img_buf_before, x=15, w=180)
        pdf.ln(2)

        # Import / Export après
        img_buf_after = BytesIO()
        fig_after.savefig(img_buf_after, format="png")
        img_buf_after.seek(0)
        pdf.image(img_buf_after, x=15, w=180)

        # -------------------------
        # EXPORT PDF Streamlit
        # -------------------------
        pdf_buffer = BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)
        st.download_button(
            "📥 Télécharger PDF client",
            pdf_buffer,
            file_name="simulation_batterie_client.pdf",
            mime="application/pdf"
        )

    st.success("PDF client généré ! ✅")
