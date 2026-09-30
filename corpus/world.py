"""The synthetic world. Every company, person, office and address is FICTITIOUS.

All e-mail/PEC domains use the reserved ``.example`` TLD (RFC 2606). No tax
codes, VAT numbers, IBANs or court case numbers appear anywhere; references
use the visibly synthetic ``SYN-`` / ``PR-`` / ``EX-`` prefixes.
Canonical names are written out by hand (not computed) so the gold labels are
independent of ``pipeline.entities.canonical``.
"""

DEBTOR = {
    "name": "Fornace Aurelia S.r.l.",
    "canonical": "FORNACE AURELIA S.R.L.",
    "aliases": ["Fornace Aurelia S.r.l.", "FORNACE AURELIA SRL", "Fornace Aurelia s.r.l.", "Fornace Aurelia"],
    "pec": "fornaceaurelia@pec.fornaceaurelia.example",
    "forward_pec": "protocollo@pec.fornaceaurelia.example",
    "domains": ["fornaceaurelia.example"],
}

CREDITORS = [
    {"key": "TM", "name": "Tessiture Monteverde S.r.l.", "canonical": "TESSITURE MONTEVERDE S.R.L.", "pec": "amministrazione@pec.tessituremonteverde.example"},
    {"key": "OL", "name": "Officine Lagorai S.r.l.", "canonical": "OFFICINE LAGORAI S.R.L.", "pec": "crediti@pec.officinelagorai.example"},
    {"key": "CB", "name": "Cantine Belvedere S.p.A.", "canonical": "CANTINE BELVEDERE S.P.A.", "pec": "contabilita@pec.cantinebelvedere.example"},
    {"key": "CR", "name": "Carpenterie Rovere S.r.l.", "canonical": "CARPENTERIE ROVERE S.R.L.", "pec": "amministrazione@pec.carpenterierovere.example"},
    {"key": "LC", "name": "Laterizi Corvara S.n.c. di Bruno Ferlenghi & C.", "canonical": "LATERIZI CORVARA S.N.C. DI BRUNO FERLENGHI & C.", "pec": "info@pec.laterizicorvara.example"},
    {"key": "VE", "name": "Società Agricola Valle dell'Èrto S.S.", "canonical": "SOCIETÀ AGRICOLA VALLE DELL’ÈRTO S.S.", "pec": "segreteria@pec.valledellerto.example"},
    {"key": "AG", "name": "Autotrasporti Ghiaiola S.r.l.", "canonical": "AUTOTRASPORTI GHIAIOLA S.R.L.", "pec": "amministrazione@pec.ghiaiola.example"},
    {"key": "FO", "name": "Forniture dell’Ontano S.r.l.", "canonical": "FORNITURE DELL’ONTANO S.R.L.", "pec": "ufficio.crediti@pec.fornitureontano.example"},
    {"key": "CP", "name": "Ceramiche Pontalba S.a.s. di Rita Morlacchi & C.", "canonical": "CERAMICHE PONTALBA S.A.S. DI RITA MORLACCHI & C.", "pec": "info@pec.ceramichepontalba.example"},
    {"key": "SV", "name": "Cooperativa Sentiero Verde Soc. Coop.", "canonical": "COOPERATIVA SENTIERO VERDE SOC. COOP.", "pec": "amministrazione@pec.sentieroverde.example"},
]

LAWYERS = [
    {"key": "IM", "name": "Ilaria Moscardini", "canonical": "ILARIA MOSCARDINI (AVV.)", "studio": "STUDIO LEGALE MOSCARDINI",
     "pec": "ilaria.moscardini@pec.ordineavvocati-esempio.example", "display": "Avv. Ilaria Moscardini", "cert": "trusted"},
    {"key": "TO", "name": "Tancredi Olivieri", "canonical": "TANCREDI OLIVIERI (AVV.)", "studio": "STUDIO OLIVIERI",
     "pec": "studio.olivieri@pec.professionisti.example", "display": "Studio Olivieri", "cert": "trusted",
     "transmitter_canonical": "STUDIO OLIVIERI"},
    {"key": "SL", "name": "Serena Lupatelli", "canonical": "SERENA LUPATELLI (AVV.)", "studio": "STUDIO LEGALE LUPATELLI",
     "pec": "avv.serenalupatelli@pec.legalmail-esempio.example", "display": "Avv. Serena Lupatelli", "cert": "untrusted"},
    {"key": "DM", "name": "Donato Mariscotti", "canonical": "DONATO MARISCOTTI (AVV.)", "studio": "STUDIO LEGALE MARISCOTTI",
     "pec": "donato.mariscotti@pec.ordineavvocati-esempio.example", "display": "Avv. Donato Mariscotti", "cert": "expires-2026-07-31"},
]

GATEWAYS = [
    {"key": "ND", "name": "Servizi Notifiche Digitali Esempio S.p.A.", "canonical": "SERVIZI NOTIFICHE DIGITALI ESEMPIO S.P.A.",
     "pec": "notifiche@pec.notifichedigitali.example"},
    {"key": "GP", "name": "Gateway PEC Esempio S.r.l.", "canonical": "GATEWAY PEC ESEMPIO S.R.L.",
     "pec": "invii@pec.gateway-esempio.example"},
]

COURT = {"name": "Tribunale di Esempio", "canonical": "TRIBUNALE DI ESEMPIO",
         "offices": {
             "esecuzioni": ("Tribunale di Esempio - Cancelleria Esecuzioni", "esecuzioni.civili@civile.tribunale.example"),
             "crisi": ("Tribunale di Esempio - Sezione Crisi d'Impresa", "crisi.impresa@civile.tribunale.example"),
             "contenzioso": ("Tribunale di Esempio - Cancelleria Contenzioso", "contenzioso@civile.tribunale.example"),
         }}

AGENCY = {"name": "Agenzia Esempio Riscossione", "canonical": "AGENZIA ESEMPIO RISCOSSIONE",
          "pec": "notifica.cartelle@pec.agenzia-riscossione.example",
          "contact": "protocollo@pec.agenzia-riscossione.example"}
TAX_OFFICE = {"name": "Agenzia Esempio Entrate", "canonical": "AGENZIA ESEMPIO ENTRATE",
              "pec": "dp.esempio@pec.agenzia-entrate-esempio.example"}
MUNICIPALITY = {"name": "Comune di Esempio", "canonical": "COMUNE DI ESEMPIO", "pec": "tributi@pec.comune-esempio.example"}
SOCIAL = {"name": "Istituto Esempio Previdenza", "canonical": "ISTITUTO ESEMPIO PREVIDENZA",
          "pec": "direzione.esempio@pec.previdenza-esempio.example"}

BANKS = [
    {"key": "BA", "name": "Banca Aurora Esempio S.p.A.", "canonical": "BANCA AURORA ESEMPIO S.P.A.", "pec": "legale@pec.bancaaurora.example"},
    {"key": "CV", "name": "Credito Cooperativo Valfiorita", "canonical": "CREDITO COOPERATIVO VALFIORITA", "pec": "segreteria@pec.creditovalfiorita.example"},
]

GESTORI = [
    {"key": "G1", "name": "GESTORE PEC ESEMPIO S.P.A.", "addr": "posta-certificata@pec.gestore-uno.example", "domain": "pec.gestore-uno.example"},
    {"key": "G2", "name": "POSTACERTA ESEMPIO S.R.L.", "addr": "posta-certificata@postacerta-esempio.example", "domain": "postacerta-esempio.example"},
]
