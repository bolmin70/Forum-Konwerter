"""Convert WAPRO MAG (MAGIK) XML invoice exports to Comarch Optima offline format."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from xml.dom import minidom

WAPRO_EPOCH = date(1800, 12, 28)
OPTIMA_NS = "http://www.comarch.pl/cdn/optima/offline"
ET.register_namespace("", OPTIMA_NS)


def wapro_date_to_iso(value: str | int | None) -> str:
    if value in (None, "", "0"):
        return ""
    days = int(str(value).strip())
    return (WAPRO_EPOCH + timedelta(days=days)).isoformat()


def wapro_date_to_yyyymm(value: str | int | None) -> str:
    iso = wapro_date_to_iso(value)
    return iso[:7] if iso else ""


def normalize_amount(value: str | None, decimals: int = 2) -> str:
    if value is None or value == "":
        return f"{0:.{decimals}f}"
    s = value.strip()
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-."):
        s = "-0" + s[1:]
    try:
        return f"{float(s):.{decimals}f}"
    except ValueError:
        return s


def normalize_vat_code(code: str | None) -> str:
    if not code:
        return ""
    code = code.strip()
    if code.lower() in ("zw", "np", "oo"):
        return code.lower()
    digits = re.sub(r"[^\d]", "", code)
    return digits or code


@dataclass
class Address:
    nazwa1: str = ""
    nazwa2: str = ""
    nazwa3: str = ""
    ulica: str = ""
    nr_domu: str = ""
    nr_lokalu: str = ""
    kod_pocztowy: str = ""
    miasto: str = ""
    poczta: str = ""
    nip: str = ""
    kraj_iso: str = ""


@dataclass
class Party:
    id_: str = ""
    akronim: str = ""
    finalny: bool = False
    address: Address = field(default_factory=Address)


@dataclass
class VatLine:
    stawka: str = "23"
    netto: float = 0.0
    vat: float = 0.0


@dataclass
class Document:
    numer: str = ""
    data_wystawienia: str = ""
    data_sprzedazy: str = ""
    termin_platnosci: str = ""
    forma_platnosci: str = "przelew"
    waluta: str = ""
    brutto: float = 0.0
    netto: float = 0.0
    vat_lines: list[VatLine] = field(default_factory=list)
    jpk_codes: list[str] = field(default_factory=list)
    podatnik_czynny: bool = True
    kontrahent: Party = field(default_factory=Party)
    is_correction: bool = False
    correction_number: str = ""
    nr_ksef: str = ""
    ksef_data_przyjecia: str = ""
    rodzaj_korekty_1: bool = False


def split_address(ulica_lokal: str) -> tuple[str, str, str]:
    """Split 'Grzegorzecka 67d/50' into ('Grzegorzecka', '67d', '50')."""
    if not ulica_lokal:
        return "", "", ""
    s = ulica_lokal.strip()

    m = re.match(
        r"^(?P<street>.+?)\s+(?P<num>\d+[A-Za-z]?)(?:\s*/\s*(?P<lokal>[\w\d]+))?$",
        s,
    )
    if m:
        return m.group("street").strip(), m.group("num"), m.group("lokal") or ""

    parts = s.rsplit(" ", 1)
    if len(parts) == 2 and re.search(r"\d", parts[1]):
        return parts[0], parts[1], ""
    return s, "", ""


def map_forma_platnosci(forma: str) -> str:
    if not forma:
        return "przelew"
    f = forma.lower()
    if "przelew" in f:
        return "przelew"
    if "got" in f:
        return "gotówka"
    if "karta" in f or "card" in f:
        return "karta"
    if "kompensata" in f:
        return "kompensata"
    return forma.strip()


def parse_kontrahenci(root: ET.Element) -> dict[str, Party]:
    out: dict[str, Party] = {}
    kart = root.find("KARTOTEKA_KONTRAHENTOW")
    if kart is None:
        return out

    for k in kart.findall("KONTRAHENT"):
        kid = (k.findtext("ID_KONTRAHENTA") or "").strip()
        nip = (k.findtext("NIP") or "").strip()
        nazwa_pelna = (k.findtext("NAZWA_PELNA") or k.findtext("NAZWA") or "").strip()
        miasto = (k.findtext("MIEJSCOWOSC") or "").strip()
        kod_pocztowy = (k.findtext("KOD_POCZTOWY") or "").strip()
        ulica_lokal = (k.findtext("ULICA_LOKAL") or "").strip()
        kraj = (k.findtext("SYMBOL_KRAJU_KONTRAHENTA") or "").strip()

        ulica, nr_domu, nr_lokalu = split_address(ulica_lokal)

        nazwa_lines = nazwa_pelna.replace("\r\n", "\n").split("\n")
        nazwa1 = nazwa_lines[0] if nazwa_lines else ""
        nazwa2 = nazwa_lines[1] if len(nazwa_lines) > 1 else ""
        nazwa3 = nazwa_lines[2] if len(nazwa_lines) > 2 else ""

        if nip:
            akronim = nip
        elif nazwa1:
            akronim = re.sub(r"\s+", " ", nazwa1).strip().upper()
        else:
            akronim = kid
        party = Party(
            id_=kid,
            akronim=akronim,
            finalny=False,
            address=Address(
                nazwa1=nazwa1,
                nazwa2=nazwa2,
                nazwa3=nazwa3,
                ulica=ulica,
                nr_domu=nr_domu,
                nr_lokalu=nr_lokalu,
                kod_pocztowy=kod_pocztowy,
                miasto=miasto,
                poczta=miasto,
                nip=nip,
                kraj_iso=kraj,
            ),
        )
        out[kid] = party
    return out


def parse_document(doc: ET.Element, kontrahenci: dict[str, Party]) -> Document:
    naglowek = doc.find("NAGLOWEK_DOKUMENTU")
    if naglowek is None:
        raise ValueError("Brak NAGLOWEK_DOKUMENTU w dokumencie")

    numer = (naglowek.findtext("NUMER") or "").strip()
    id_kontrahenta = (naglowek.findtext("ID_KONTRAHENTA") or "").strip()
    id_platnika = (naglowek.findtext("ID_PLATNIKA") or "").strip()
    forma = (naglowek.findtext("FORMA_PLATNOSCI") or "").strip()
    waluta = (naglowek.findtext("SYM_WAL") or "PLN").strip()
    if waluta.upper() == "PLN":
        waluta = ""

    is_correction = (naglowek.findtext("CZY_DOKUMENT_KOREKTY") or "0").strip() == "1"

    daty = naglowek.find("DATY")
    if daty is None:
        raise ValueError(f"Brak elementu DATY w dokumencie {numer}")
    data_wystawienia = wapro_date_to_iso(daty.findtext("DATA_WYSTAWIENIA"))
    data_sprzedazy = wapro_date_to_iso(daty.findtext("DATA_SPRZEDAZY"))
    termin = wapro_date_to_iso(daty.findtext("TERMIN_PLATNOSCI"))

    wartosci = naglowek.find("WARTOSCI_NAGLOWKA")
    netto = float(normalize_amount(wartosci.findtext("NETTO_SPRZEDAZY") if wartosci is not None else "0", 4))
    brutto = float(normalize_amount(wartosci.findtext("BRUTTO_SPRZEDAZY") if wartosci is not None else "0", 4))

    rodzaj = (naglowek.findtext("RODZAJ_TRANSAKCJI_HANDLOWEJ") or "").strip()
    jpk_codes: list[str] = []
    if rodzaj:
        for token in re.split(r"[,;\s]+", rodzaj):
            t = token.strip()
            if t and t not in jpk_codes:
                jpk_codes.append(t)

    vat_lines: list[VatLine] = []
    vat_root = doc.find("VAT")
    if vat_root is not None:
        for stawka in vat_root.findall("STAWKA"):
            kod = normalize_vat_code(stawka.findtext("KOD_VAT"))
            n = float(normalize_amount(stawka.findtext("NETTO"), 4))
            v = float(normalize_amount(stawka.findtext("VAT"), 4))
            if kod or n or v:
                vat_lines.append(VatLine(stawka=kod or "23", netto=n, vat=v))

    if not vat_lines:
        vat_lines.append(VatLine(stawka="23", netto=netto, vat=brutto - netto))

    rodzaj_korekty_1 = False
    pozycje_root = doc.find("POZYCJE_DOKUMENTU")
    if pozycje_root is not None:
        for poz in pozycje_root.findall("POZYCJA_DOKUMENTU"):
            if (poz.findtext("RODZAJ_KOREKTY") or "").strip() == "1":
                rodzaj_korekty_1 = True
                break

    pid = id_platnika if id_platnika and id_platnika != "0" else id_kontrahenta
    party = kontrahenci.get(pid) or kontrahenci.get(id_kontrahenta) or Party(id_=pid, akronim=pid or "Nieznany")

    nr_ksef = ""
    ksef_data_przyjecia = ""
    ksef_el = naglowek.find("KSEF")
    if ksef_el is not None:
        nr_ksef = (ksef_el.findtext("KSEF_ID") or "").strip()
        ksef_data_przyjecia = wapro_date_to_iso(
            ksef_el.findtext("DATA_POTW_KSEF") or ksef_el.findtext("DATA_WYSLANIA_KSEF")
        )

    return Document(
        numer=numer,
        data_wystawienia=data_wystawienia,
        data_sprzedazy=data_sprzedazy,
        termin_platnosci=termin or data_sprzedazy,
        forma_platnosci=map_forma_platnosci(forma),
        waluta=waluta,
        brutto=brutto,
        netto=netto,
        vat_lines=vat_lines,
        jpk_codes=jpk_codes,
        kontrahent=party,
        is_correction=is_correction,
        nr_ksef=nr_ksef,
        ksef_data_przyjecia=ksef_data_przyjecia,
        rodzaj_korekty_1=rodzaj_korekty_1,
    )


def parse_input(xml_path: Path) -> tuple[list[Document], dict[str, Party]]:
    raw = xml_path.read_bytes()
    text = _decode_xml(raw)
    root = ET.fromstring(text)
    kontrahenci = parse_kontrahenci(root)
    documents: list[Document] = []
    for doc in root.findall("DOKUMENTY/DOKUMENT"):
        documents.append(parse_document(doc, kontrahenci))
    return documents, kontrahenci


def _decode_xml(raw: bytes) -> str:
    decl_match = re.match(rb"^\s*<\?xml[^>]*encoding=[\"']([^\"']+)[\"']", raw)
    encoding = decl_match.group(1).decode("ascii").lower() if decl_match else "utf-8"
    aliases = {"windows-1250": "cp1250", "iso-8859-2": "iso-8859-2", "utf-8": "utf-8"}
    py_enc = aliases.get(encoding, encoding)
    try:
        text = raw.decode(py_enc)
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("cp1250", errors="replace")
    return re.sub(r"<\?xml[^>]*\?>", "", text, count=1).lstrip()


def _ce(parent: ET.Element, tag: str, text: str = "", cdata: bool = False) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if cdata:
        el.text = f"<![CDATA[{text}]]>"
    else:
        el.text = text
    return el


def build_optima_tree(
    documents: Iterable[Document],
    parties: dict[str, Party],
    *,
    rejestr: str = "SP",
    kategoria: str = "730-1",
    base_zrd_id: str = "BZ",
    base_doc_id: str = "K1",
    include_detal: bool = True,
) -> ET.ElementTree:
    root = ET.Element(f"{{{OPTIMA_NS}}}ROOT")

    docs = list(documents)
    used_ids = {d.kontrahent.id_ for d in docs if d.kontrahent and d.kontrahent.id_}

    kontrahenci_el = ET.SubElement(root, "KONTRAHENCI")
    _ce(kontrahenci_el, "WERSJA", "2.00")
    _ce(kontrahenci_el, "BAZA_ZRD_ID", base_zrd_id, cdata=True)
    _ce(kontrahenci_el, "BAZA_DOC_ID", base_doc_id, cdata=True)

    if include_detal:
        _append_kontrahent(
            kontrahenci_el,
            Party(
                id_="DETAL",
                akronim="Sprzedaż detaliczna",
                finalny=True,
                address=Address(nazwa1="Sprzedaż detaliczna"),
            ),
        )

    seen: set[str] = set()
    for kid in used_ids:
        party = parties.get(kid)
        if not party or party.akronim in seen:
            continue
        seen.add(party.akronim)
        _append_kontrahent(kontrahenci_el, party)

    rzv = ET.SubElement(root, "REJESTRY_ZAKUPU_VAT")
    _ce(rzv, "WERSJA", "2.00")
    _ce(rzv, "BAZA_ZRD_ID", base_zrd_id, cdata=True)
    _ce(rzv, "BAZA_DOC_ID", base_doc_id, cdata=True)

    rsv = ET.SubElement(root, "REJESTRY_SPRZEDAZY_VAT")
    _ce(rsv, "WERSJA", "2.00")
    _ce(rsv, "BAZA_ZRD_ID", base_zrd_id, cdata=True)
    _ce(rsv, "BAZA_DOC_ID", base_doc_id, cdata=True)

    for d in docs:
        _append_rejestr(rsv, d, rejestr=rejestr, kategoria=kategoria)

    return ET.ElementTree(root)


def _append_kontrahent(parent: ET.Element, party: Party) -> None:
    k = ET.SubElement(parent, "KONTRAHENT")
    _ce(k, "AKRONIM", party.akronim, cdata=True)
    _ce(k, "KRAJ_ISO", party.address.kraj_iso)
    _ce(k, "FINALNY", "Tak" if party.finalny else "Nie")
    addresses = ET.SubElement(k, "ADRESY")
    a = ET.SubElement(addresses, "ADRES")
    _ce(a, "NAZWA1", party.address.nazwa1, cdata=True)
    _ce(a, "NAZWA2", party.address.nazwa2)
    _ce(a, "NAZWA3", party.address.nazwa3)
    _ce(a, "ULICA", party.address.ulica, cdata=True)
    _ce(a, "NR_DOMU", party.address.nr_domu, cdata=True)
    _ce(a, "NR_LOKALU", party.address.nr_lokalu, cdata=True)
    _ce(a, "KOD_POCZTOWY", party.address.kod_pocztowy, cdata=True)
    _ce(a, "MIASTO", party.address.miasto, cdata=True)
    _ce(a, "NIP", party.address.nip, cdata=True)


def _append_rejestr(parent: ET.Element, d: Document, *, rejestr: str, kategoria: str) -> None:
    r = ET.SubElement(parent, "REJESTR_SPRZEAZY_VAT")
    _ce(r, "MODUL", "Rejestr Vat")
    _ce(r, "TYP", "Rejestr sprzedazy")
    _ce(r, "REJESTR", rejestr, cdata=True)
    _ce(r, "DATA_WYSTAWIENIA", d.data_wystawienia)
    _ce(r, "DATA_SPRZEDAZY", d.data_sprzedazy)
    _ce(r, "TERMIN", d.termin_platnosci)
    _ce(r, "DATA_DATAOBOWIAZKUPODATKOWEGO", d.data_sprzedazy)
    _ce(r, "DATA_DATAPRAWAODLICZENIA", d.data_sprzedazy)
    _ce(r, "NUMER", d.numer, cdata=True)
    _ce(r, "KOREKTA", "Tak" if d.is_correction else "Nie")
    _ce(r, "KOREKTA_NUMER", d.correction_number)
    if d.nr_ksef:
        _ce(r, "NR_KSEF", d.nr_ksef, cdata=True)
    if d.ksef_data_przyjecia:
        _ce(r, "KSEF_DATA_PRZYJECIA", d.ksef_data_przyjecia, cdata=True)
    _ce(r, "EKSPORT", "nie")
    _ce(r, "FINALNY", "Tak" if d.kontrahent.finalny else "Nie")
    _ce(r, "PODATNIK_CZYNNY", "Tak" if d.podatnik_czynny else "Nie")
    _ce(r, "TYP_PODMIOTU", "kontrahent")
    _ce(r, "PODMIOT", d.kontrahent.akronim, cdata=True)
    _ce(r, "PODMIOT_NIP", d.kontrahent.address.nip, cdata=True)
    _ce(r, "NAZWA1", d.kontrahent.address.nazwa1, cdata=True)
    _ce(r, "NAZWA2", d.kontrahent.address.nazwa2)
    _ce(r, "NAZWA3", d.kontrahent.address.nazwa3)
    _ce(r, "NIP_KRAJ", d.kontrahent.address.kraj_iso if d.kontrahent.address.nip else "")
    _ce(r, "NIP", d.kontrahent.address.nip, cdata=True)
    _ce(r, "ULICA", d.kontrahent.address.ulica, cdata=True)
    _ce(r, "NR_DOMU", d.kontrahent.address.nr_domu, cdata=True)
    _ce(r, "NR_LOKALU", d.kontrahent.address.nr_lokalu, cdata=True)
    _ce(r, "MIASTO", d.kontrahent.address.miasto, cdata=True)
    _ce(r, "KOD_POCZTOWY", d.kontrahent.address.kod_pocztowy, cdata=True)
    _ce(r, "POCZTA", d.kontrahent.address.poczta, cdata=True)
    _ce(r, "KATEGORIA", kategoria, cdata=True)
    _ce(r, "FORMA_PLATNOSCI", d.forma_platnosci)
    _ce(r, "DEKLARACJA_VAT7", d.data_wystawienia[:7])
    _ce(r, "DEKLARACJA_VATUE", "Nie")
    _ce(r, "WALUTA", d.waluta, cdata=True)
    _ce(r, "KURS_WALUTY", "NBP")
    _ce(r, "NOTOWANIE_WALUTY_ILE", "1")
    _ce(r, "NOTOWANIE_WALUTY_ZA_ILE", "1")
    _ce(r, "DATA_KURSU", d.data_wystawienia)

    pozycje = ET.SubElement(r, "POZYCJE")
    for line in d.vat_lines:
        p = ET.SubElement(pozycje, "POZYCJA")
        _ce(p, "KATEGORIA_POS", kategoria, cdata=True)
        _ce(p, "STAWKA_VAT", line.stawka)
        _ce(p, "STATUS_VAT", _status_vat(line.stawka))
        _ce(p, "NETTO", f"{line.netto:.2f}")
        _ce(p, "VAT", f"{line.vat:.2f}")
        _ce(p, "NETTO_SYS", f"{line.netto:.2f}")
        _ce(p, "VAT_SYS", f"{line.vat:.2f}")
        _ce(p, "NETTO_SYS2", f"{line.netto:.2f}")
        _ce(p, "VAT_SYS2", f"{line.vat:.2f}")
        _ce(p, "RODZAJ_SPRZEDAZY", "towary")
        _ce(p, "UWZ_W_PROPORCJI", "tak")
        _ce(p, "OPIS_POS", kategoria, cdata=True)

    platnosci = ET.SubElement(r, "PLATNOSCI")
    pl = ET.SubElement(platnosci, "PLATNOSC")
    kwota_plat = abs(d.brutto) if d.rodzaj_korekty_1 else d.brutto
    _ce(pl, "TERMIN_PLAT", d.termin_platnosci)
    _ce(pl, "FORMA_PLATNOSCI_PLAT", d.forma_platnosci)
    _ce(pl, "KWOTA_PLAT", f"{kwota_plat:.2f}")
    _ce(pl, "WALUTA_PLAT", d.waluta, cdata=True)
    _ce(pl, "KURS_WALUTY_PLAT", "NBP")
    _ce(pl, "NOTOWANIE_WALUTY_ILE_PLAT", "1")
    _ce(pl, "NOTOWANIE_WALUTY_ZA_ILE_PLAT", "1")
    _ce(pl, "KWOTA_PLN_PLAT", f"{kwota_plat:.2f}")
    _ce(pl, "KIERUNEK", "przychód")
    _ce(pl, "PODLEGA_ROZLICZENIU", "tak")
    _ce(pl, "DATA_KURSU_PLAT", d.data_wystawienia)
    _ce(pl, "WALUTA_DOK", d.waluta, cdata=True)
    _ce(pl, "PLATNOSC_TYP_PODMIOTU", "kontrahent")
    _ce(pl, "PLATNOSC_PODMIOT", d.kontrahent.akronim, cdata=True)
    _ce(pl, "PLATNOSC_PODMIOT_NIP", d.kontrahent.address.nip, cdata=True)

    _ce(r, "MPP", "Nie")

    if d.jpk_codes:
        kody = ET.SubElement(r, "KODY_JPK")
        for code in d.jpk_codes:
            kj = ET.SubElement(kody, "KOD_JPK")
            _ce(kj, "KOD", code, cdata=True)


def _status_vat(stawka: str) -> str:
    s = (stawka or "").lower()
    if s in ("zw", "zwolniona"):
        return "zwolniona"
    if s in ("np", "0"):
        return "opodatkowana" if s == "0" else "nie podlega"
    if s == "oo":
        return "opodatkowana"
    return "opodatkowana"


def _serialize(tree: ET.ElementTree) -> bytes:
    raw = ET.tostring(tree.getroot(), encoding="unicode")
    pretty = minidom.parseString(raw.encode("utf-8")).toprettyxml(indent="", newl="\n", encoding=None)
    pretty = _unwrap_cdata(pretty)
    pretty_lines = [ln for ln in pretty.splitlines() if ln.strip()]
    body = "\n".join(pretty_lines[1:])
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def _unwrap_cdata(text: str) -> str:
    def _unescape(payload: str) -> str:
        return (
            payload.replace("&quot;", '"')
            .replace("&apos;", "'")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&amp;", "&")
        )

    return re.sub(
        r">&lt;!\[CDATA\[(.*?)\]\]&gt;<",
        lambda m: f"><![CDATA[{_unescape(m.group(1))}]]><",
        text,
        flags=re.DOTALL,
    )


def make_output_filename(input_path: Path, initials: str, when: date | None = None) -> str:
    stem = input_path.stem
    when = when or date.today()
    initials = (initials or "").strip().upper() or "USR"
    return f"SPR_{stem}-{initials}-{when.strftime('%Y%m%d')}.xml"


@dataclass
class ConvertOptions:
    initials: str = ""
    rejestr: str = "SP"
    kategoria: str = "730-1"
    base_zrd_id: str = "BZ"
    base_doc_id: str = "K1"
    include_detal: bool = True
    output_dir: Path | None = None
    when: date | None = None


def convert_file(input_path: Path, opts: ConvertOptions) -> Path:
    documents, parties = parse_input(input_path)
    if not documents:
        raise ValueError(f"Brak dokumentów do konwersji w pliku {input_path.name}")

    tree = build_optima_tree(
        documents,
        parties,
        rejestr=opts.rejestr,
        kategoria=opts.kategoria,
        base_zrd_id=opts.base_zrd_id,
        base_doc_id=opts.base_doc_id,
        include_detal=opts.include_detal,
    )
    payload = _serialize(tree)

    out_dir = opts.output_dir or input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = make_output_filename(input_path, opts.initials, opts.when)
    out_path = out_dir / out_name
    out_path.write_bytes(payload)
    return out_path
