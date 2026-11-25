"""DMV Experts v0.4 - veilige ontvangst van ZIP-pakketten uit gesynchroniseerde Dropbox.
Python >=3.10; alleen standaardbibliotheek. Geen automatische Word-verwerking.
"""
import argparse
import hashlib
import json
import logging
import re
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT_DEFAULT = r'C:\Users\Dirk De Meyer\DDM Architectuur\Data - Documenten\0000 DMV experts'
PATTERN = re.compile(r'^(\d{6})_(\d{7})_([^\\/:*?"<>|]+)$')
ALLOWED = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.mp4', '.mov', '.webm', '.m4a', '.wav', '.mp3', '.ogg', '.txt', '.json', '.doc', '.docx', '.pdf'}

def digest(f):
    h = hashlib.sha256()
    with open(f, 'rb') as source:
        for data in iter(lambda: source.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()

def import_zip(archive: Path, root: Path, cleanup=False):
    # Expect 261126_2609459_Hendriks_000002.zip; only archive and its contents
    # are staged in Dropbox. Extraction happens in local temp, never directly into dossiers.
    if not archive.name.lower().endswith('.zip'):
        raise ValueError('Geen ZIP')
    with zipfile.ZipFile(archive) as z:
        names = [i for i in z.infolist() if not i.is_dir()]
        if not names or len(names) > 2000:
            raise ValueError('Leeg of te veel bestanden')
        first_parts = [PurePosixPath(i.filename).parts for i in names]
        if any(len(p) != 2 or any(k in ('.', '..', '') or '\\' in k for k in p) for p in first_parts):
            raise ValueError('Onveilige mapstructuur in ZIP')
        folder = first_parts[0][0]
        if any(p[0] != folder for p in first_parts):
            raise ValueError('Meerdere dossiers in één pakket')
        m = PATTERN.fullmatch(folder)
        if not m:
            raise ValueError('Ongeldige dossiermap')
        datetime.strptime(m[1], '%y%m%d')
        # Accepteer exacte exportnaam, Windows-duplicaat (2), en genummerde app-export.
        # De map IN de ZIP en dossier.json blijven de gezaghebbende controles.
        archive_stem = re.sub(r' \(\d+\)$', '', archive.stem)
        if not (archive_stem == folder or archive_stem.startswith(folder + '_')):
            raise ValueError('Pakketnaam hoort niet bij dossier')
        allfiles = {p[1]: i for p, i in zip(first_parts, names)}
        if len(allfiles) != len(names) or 'dossier.json' not in allfiles:
            raise ValueError('Dubbele namen of dossiergegevens ontbreken')
        meta = json.loads(z.read(allfiles['dossier.json']))
        if str(meta.get('dossier')) != m[2] or str(meta.get('datum','')).replace('-','')[2:] != m[1] or meta.get('map') != folder:
            raise ValueError('Dossiernummer of expertisedatum stemt niet overeen')
        # Guard against ZIP bombs and unexpected paths.
        if sum(i.file_size for i in names) > 1024*1024*1024:
            raise ValueError('Pakket te groot')
        if any(PurePosixPath(p[1]).suffix.lower() not in ALLOWED for p in first_parts):
            raise ValueError('Niet toegestaan bestandstype')
        matching = [x for x in root.iterdir() if x.is_dir() and (mm := PATTERN.fullmatch(x.name)) and mm[1] == m[1] and mm[2] == m[2]]
        if len(matching) > 1:
            raise ValueError('Meerdere bestaande dossiermappen met dezelfde code en expertisedatum')
        dest = matching[0] if matching else root / folder
        dest.mkdir(parents=True, exist_ok=True)
        count = 0
        for item in names:
            fn = PurePosixPath(item.filename).name
            # Filename can be untrusted; reject control chars and Windows reserved chars.
            if not fn or any(c in fn for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in fn):
                raise ValueError('Ongeldige bestandsnaam')
            target = dest / fn
            tmp = dest / (fn + '.dmvpart')
            with z.open(item) as src, tmp.open('wb') as out:
                shutil.copyfileobj(src, out, 1024*1024)
            srcsum = digest(tmp)
            if target.exists():
                if digest(target) == srcsum:
                    tmp.unlink()
                    continue
                target = dest / (Path(fn).stem + '__' + srcsum[:12] + Path(fn).suffix)
                if target.exists():
                    if digest(target) != srcsum:
                        tmp.unlink()
                        raise ValueError('Naamconflict')
                    tmp.unlink()
                    continue
            tmp.rename(target)
            if digest(target) != srcsum:
                raise IOError('Controle van kopie mislukt')
            count += 1
    logging.info('Controle geslaagd: %s, %s nieuwe bestanden in %s', archive.name, count, dest)
    if cleanup:
        archive.unlink()  # Dropbox desktop synchroniseert deze verwijdering met cloud-inbox.
        logging.info('Tijdelijke Dropbox-kopie verwijderd: %s', archive.name)
    return count

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inbox', required=True, help='Dropbox lokale gesynchroniseerde map DMV_TRANSFER')
    ap.add_argument('--root', default=ROOT_DEFAULT)
    ap.add_argument('--interval', type=int, default=60)
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--cleanup', action='store_true', help='Na volledige controle de ZIP uit tijdelijke Dropbox-map verwijderen')
    a = ap.parse_args()
    inbox, root = Path(a.inbox), Path(a.root)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if not root.is_dir(): ap.error('DMV-hoofdmap bestaat niet: '+str(root))
    if not inbox.is_dir(): ap.error('Dropbox-map bestaat niet: '+str(inbox))
    while True:
        for f in sorted(inbox.glob('*.zip')):
            try:
                # Wacht op stabiliteit; Dropbox kan bestand nog downloaden.
                s1 = f.stat().st_size
                time.sleep(2)
                if not f.exists() or f.stat().st_size != s1: continue
                import_zip(f, root, cleanup=a.cleanup)
            except Exception:
                logging.exception('Ontvangst mislukt voor %s. Bestand blijft in Dropbox staan.', f.name)
        if a.once: break
        time.sleep(max(15, a.interval))

if __name__ == '__main__': main()
