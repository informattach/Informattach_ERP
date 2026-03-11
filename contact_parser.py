import pandas as pd
import uuid
import re
from typing import List, Dict, Any, Tuple
from database import db

# Standartlaştırılmış Veri Modelleri
class ContactAddress:
    def __init__(self, address_type='other', address_line_1='', address_line_2='', city='', state_region='', postal_code='', country_code=''):
        self.address_type = address_type
        self.address_line_1 = address_line_1
        self.address_line_2 = address_line_2
        self.city = city
        self.state_region = state_region
        self.postal_code = postal_code
        self.country_code = country_code
        
    def to_dict(self):
        return {
            "address_type": self.address_type,
            "address_line_1": self.address_line_1,
            "address_line_2": self.address_line_2,
            "city": self.city,
            "state_region": self.state_region,
            "postal_code": self.postal_code,
            "country_code": self.country_code
        }

class ContactRecord:
    def __init__(self, contact_type='other', source_platform='manual', external_id=None, first_name='', last_name='', company_name='', email='', phone=''):
        self.contact_type = contact_type
        self.source_platform = source_platform
        self.external_id = external_id
        self.first_name = first_name
        self.last_name = last_name
        self.company_name = company_name
        self.email = email
        self.phone = phone
        self.addresses: List[ContactAddress] = []
        self.attributes: Dict[str, Any] = {}

    def to_dict(self):
        return {
            "contact_type": self.contact_type,
            "source_platform": self.source_platform,
            "external_id": self.external_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "company_name": self.company_name,
            "email": self.email,
            "phone": self.phone
        }

class BaseContactParser:
    """Temel ayrıştırıcı sınıfı."""
    def parse(self, df: pd.DataFrame) -> List[ContactRecord]:
        raise NotImplementedError("Subclasses must implement parse method")

class AmazonContactParser(BaseContactParser):
    def parse(self, df: pd.DataFrame) -> List[ContactRecord]:
        records = []
        # Amazon genel sütunları: buyer-name, buyer-phone-number, buyer-email, ship-address-1, vb.
        for _, row in df.iterrows():
            name_raw = str(row.get('buyer-name', '') or row.get('recipient-name', '')).strip()
            
            # İsim ve soyisimi ayırma (basit mantık)
            parts = name_raw.split(' ', 1)
            f_name = parts[0] if len(parts) > 0 else ''
            l_name = parts[1] if len(parts) > 1 else ''
            
            email = str(row.get('buyer-email', '')).strip()
            phone = str(row.get('buyer-phone-number', '')).strip()
            
            if not f_name and not email and not phone:
                continue
                
            record = ContactRecord(
                contact_type='customer',
                source_platform='amazon',
                first_name=f_name,
                last_name=l_name,
                email=email if email and email.lower() != 'nan' else None,
                phone=phone if phone and phone.lower() != 'nan' else None,
            )
            
            # Adres Bilgisi
            address_1 = str(row.get('ship-address-1', '')).strip()
            city = str(row.get('ship-city', '')).strip()
            state = str(row.get('ship-state', '')).strip()
            postal = str(row.get('ship-postal-code', '')).strip()
            country = str(row.get('ship-country', '')).strip()
            
            if address_1 and address_1.lower() != 'nan':
                addr = ContactAddress(
                    address_type='shipping',
                    address_line_1=address_1,
                    address_line_2=str(row.get('ship-address-2', '')).strip(),
                    city=city,
                    state_region=state,
                    postal_code=postal,
                    country_code=country
                )
                record.addresses.append(addr)
                
            records.append(record)
        return records

class EbayContactParser(BaseContactParser):
    def parse(self, df: pd.DataFrame) -> List[ContactRecord]:
        records = []
        for _, row in df.iterrows():
            # eBay genel sütunları: Buyer Username, Buyer Name, Buyer Email, Ship To Name, Ship To Address 1
            username = str(row.get('Buyer Username', '')).strip()
            name_raw = str(row.get('Buyer Name', '') or row.get('Ship To Name', '')).strip()
            
            parts = name_raw.split(' ', 1)
            f_name = parts[0] if len(parts) > 0 else ''
            l_name = parts[1] if len(parts) > 1 else ''
            
            email = str(row.get('Buyer Email', '')).strip()
            phone = str(row.get('Ship To Phone', '')).strip()
            
            if not f_name and not username:
                continue

            record = ContactRecord(
                contact_type='customer',
                source_platform='ebay',
                external_id=username if username != 'nan' else None,
                first_name=f_name,
                last_name=l_name,
                email=email if email and email.lower() != 'nan' else None,
                phone=phone if phone and phone.lower() != 'nan' else None,
            )
            
            address_1 = str(row.get('Ship To Address 1', '')).strip()
            if address_1 and address_1.lower() != 'nan':
                addr = ContactAddress(
                    address_type='shipping',
                    address_line_1=address_1,
                    address_line_2=str(row.get('Ship To Address 2', '')).strip(),
                    city=str(row.get('Ship To City', '')).strip(),
                    state_region=str(row.get('Ship To State/Province', '')).strip(),
                    postal_code=str(row.get('Ship To Zip/Postal Code', '')).strip(),
                    country_code=str(row.get('Ship To Country', '')).strip()
                )
                record.addresses.append(addr)
                
            records.append(record)
        return records

class WalmartContactParser(BaseContactParser):
    def parse(self, df: pd.DataFrame) -> List[ContactRecord]:
        records = []
        for _, row in df.iterrows():
            name_raw = str(row.get('Customer Name', '')).strip()
            parts = name_raw.split(' ', 1)
            f_name = parts[0] if len(parts) > 0 else ''
            l_name = parts[1] if len(parts) > 1 else ''
            
            email = str(row.get('Customer Email ID', '')).strip()
            phone = str(row.get('Customer Phone Number', '')).strip()
            
            if not f_name and not email:
                continue
                
            record = ContactRecord(
                contact_type='customer',
                source_platform='walmart',
                first_name=f_name,
                last_name=l_name,
                email=email if email and email.lower() != 'nan' else None,
                phone=phone if phone and phone.lower() != 'nan' else None,
            )
            
            address_1 = str(row.get('Shipping Address Line 1', '')).strip()
            if address_1 and address_1.lower() != 'nan':
                addr = ContactAddress(
                    address_type='shipping',
                    address_line_1=address_1,
                    address_line_2=str(row.get('Shipping Address Line 2', '')).strip(),
                    city=str(row.get('City', '')).strip(),
                    state_region=str(row.get('State', '')).strip(),
                    postal_code=str(row.get('Zip', '')).strip(),
                    country_code=str(row.get('Country', '')).strip() # Walmart usually provides state/zip directly
                )
                record.addresses.append(addr)
                
            records.append(record)
        return records

class AppleContactParser(BaseContactParser):
    def parse(self, df: pd.DataFrame) -> List[ContactRecord]:
        records = []
        for _, row in df.iterrows():
            # Apple OS Contacts CSV genel yapısı
            f_name = str(row.get('First Name', '')).strip()
            l_name = str(row.get('Last Name', '')).strip()
            company = str(row.get('Organization', '') or row.get('Company', '')).strip()
            
            # E-mail (Masaüstü/Ev/İş)
            email = str(row.get('E-mail Address', '') or row.get('E-mail 1 - Value', '')).strip()
            
            # Telefon
            phone = str(row.get('Primary Phone', '') or row.get('Phone 1 - Value', '')).strip()
            
            if not f_name and not l_name and not company:
                continue
                
            record = ContactRecord(
                contact_type='other',
                source_platform='apple',
                first_name=f_name,
                last_name=l_name,
                company_name=company,
                email=email if email and email.lower() != 'nan' else None,
                phone=phone if phone and phone.lower() != 'nan' else None,
            )
            records.append(record)
        return records

class GenericContactParser(BaseContactParser):
    def parse(self, df: pd.DataFrame) -> List[ContactRecord]:
        records = []
        cols = [c.lower() for c in df.columns]
        
        # Basit otomatik haritalama
        first_name_col = next((c for c in df.columns if 'first' in c.lower() and 'name' in c.lower()), None)
        last_name_col = next((c for c in df.columns if 'last' in c.lower() and 'name' in c.lower()), None)
        full_name_col = next((c for c in df.columns if c.lower() in ['name', 'isim', 'ad', 'ad soyad', 'fullname']), None)
        
        email_col = next((c for c in df.columns if 'email' in c.lower() or 'e-posta' in c.lower()), None)
        phone_col = next((c for c in df.columns if 'phone' in c.lower() or 'telefon' in c.lower() or 'tel' in c.lower()), None)
        company_col = next((c for c in df.columns if 'company' in c.lower() or 'firma' in c.lower() or 'şirket' in c.lower() or 'organization' in c.lower()), None)
        
        for _, row in df.iterrows():
            f_name = ''
            l_name = ''
            
            if first_name_col: f_name = str(row[first_name_col]).strip()
            if last_name_col: l_name = str(row[last_name_col]).strip()
            
            if not f_name and not l_name and full_name_col:
                name_raw = str(row[full_name_col]).strip()
                parts = name_raw.split(' ', 1)
                f_name = parts[0] if len(parts) > 0 else ''
                l_name = parts[1] if len(parts) > 1 else ''
                
            email = str(row[email_col]).strip() if email_col else ''
            phone = str(row[phone_col]).strip() if phone_col else ''
            company = str(row[company_col]).strip() if company_col else ''
            
            if not f_name and not email and not company:
                continue
                
            record = ContactRecord(
                contact_type='other',
                source_platform='manual',
                first_name=f_name if f_name.lower() != 'nan' else '',
                last_name=l_name if l_name.lower() != 'nan' else '',
                company_name=company if company.lower() != 'nan' else '',
                email=email if email and email.lower() != 'nan' else None,
                phone=phone if phone and phone.lower() != 'nan' else None,
            )
            records.append(record)
        return records

def detect_parser_and_parse(df: pd.DataFrame) -> Tuple[str, List[ContactRecord]]:
    """Sütun isimlerine göre dosya tipini algılar ve parse eder."""
    cols = set(df.columns)
    
    if 'buyer-name' in cols or 'ship-address-1' in cols or 'order-id' in cols and 'fulfillment-channel' in cols:
        return 'Amazon', AmazonContactParser().parse(df)
    
    if 'Buyer Username' in cols or 'Buyer Email' in cols or 'Ship To Name' in cols:
        return 'eBay', EbayContactParser().parse(df)
        
    if 'Customer Name' in cols and 'Customer Email ID' in cols:
        return 'Walmart', WalmartContactParser().parse(df)
        
    if 'First Name' in cols and ('E-mail Address' in cols or 'Organization' in cols):
        return 'Apple Contacts', AppleContactParser().parse(df)
        
    return 'Generic', GenericContactParser().parse(df)

class ContactDBManager:
    """Veritabanına (Supabase) Contacts kayıtlarını upsert yapan yönetici sınıf."""
    
    @staticmethod
    def save_records(records: List[ContactRecord]) -> Dict[str, int]:
        success_contacts = 0
        success_addresses = 0
        
        for record in records:
            # Temel kontakt verisi ve ön-işleme (Null olabilecek alanlar için)
            data = record.to_dict()
            # None olan değerleri temizleyelim (boş eklenecekse update sırasında patlamasın)
            data = {k: v for k, v in data.items() if v is not None}
            
            contact_id = None
            
            # --- Mükerrer Kontrolü (Deduplication) ---
            # Phone veya Email var ise DB'den kontrol et, varsa UPSERT / UPDATE yap
            query = db.client.table('contacts').select('id')
            match_found = False
            
            if record.email:
                res = db.client.table('contacts').select('id').eq('email', record.email).execute()
                if res.data:
                    contact_id = res.data[0]['id']
                    match_found = True
                    
            if not match_found and record.phone:
                res = db.client.table('contacts').select('id').eq('phone', record.phone).execute()
                if res.data:
                    contact_id = res.data[0]['id']
                    match_found = True
                    
            if not match_found and record.external_id:
                res = db.client.table('contacts').select('id').eq('external_id', record.external_id).execute()
                if res.data:
                    contact_id = res.data[0]['id']
                    match_found = True
            
            try:
                if match_found:
                    # Update (Upsert by returning ID)
                    data['id'] = contact_id
                    res = db.client.table('contacts').upsert(data).execute()
                else:
                    # Insert
                    res = db.client.table('contacts').insert(data).execute()
                    if res.data:
                        contact_id = res.data[0]['id']
                        
                success_contacts += 1
                
                # Adresleri Kaydet
                if contact_id and record.addresses:
                    for addr in record.addresses:
                        # Burada basitlik adına her adresi insert ediyoruz,
                        # Gerçekte benzer adres olup olmadığı denetlenebilir.
                        addr_data = addr.to_dict()
                        addr_data['contact_id'] = contact_id
                        # Adreslerde nan/null temizliği
                        addr_data = {k: v for k, v in addr_data.items() if v and v.lower() != 'nan'}
                        db.client.table('contact_addresses').insert(addr_data).execute()
                        success_addresses += 1
                        
            except Exception as e:
                print(f"Contact save error: {e}")
                
        return {"contacts_processed": success_contacts, "addresses_processed": success_addresses}
