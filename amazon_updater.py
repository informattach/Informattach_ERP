import pandas as pd
import openpyxl
import glob
import os

def prepare_amazon_file():
    print("ASIN listesi okunuyor...")
    # ASINleri oku ve filtrele (Sadece 10 haneli gerçek Amazon ASIN'leri kalsın, CJ veya TEST kodlarını sil)
    df_asins = pd.read_csv('tum_aktif_asinler_ebay_api.csv')
    raw_asins = df_asins['ASIN'].dropna().tolist()
    
    asins = []
    for asin in raw_asins:
        temp = str(asin).strip().upper()
        # Amazon ASIN'leri 10 hanelidir. TEST veya CJ ile başlayanları dışla.
        if len(temp) == 10 and not temp.startswith("TEST") and not temp.startswith("C"):
            asins.append(temp)
            
    print(f"Toplam {len(raw_asins)} üründen {len(asins)} adet saf Amazon ASIN'i filtrelendi.")

    # Klasördeki xlsx dosyalarını bul (Eskiler ve açık Excel kilit dosyaları hariç)
    xlsx_files = [f for f in glob.glob("*.xlsx") if "amazon_y" not in f.lower() and f != "exportedList.xlsx" and not f.startswith("~$")]

    if not xlsx_files:
        print("HATA: Amazon'dan yeni indirilmiş orijinal isimli Excel dosyası bulunamadı!")
        print("Lütfen dosyayı indirip İSMİNİ HİÇ DEĞİŞTİRMEDEN klasöre atın ve bu kodu tekrar çalıştırın.")
        return

    # En yeni dosyayı al (kullanıcının yeni indirdiği dosya)
    latest_file = max(xlsx_files, key=os.path.getmtime)
    print(f"Amazon'un orijinal şablonu bulundu: {latest_file}")
    print("Dosya ismine ve metadatasına dokunulmadan sadece ASIN'ler B14'ten aşağıya yapıştırılıyor...")

    wb = openpyxl.load_workbook(latest_file)
    ws = wb.active

    start_row = 14
    for idx, asin in enumerate(asins):
        # Sadece ve sadece B sütununa işlem yapıyoruz, hiçbir şeyi ellemiyoruz.
        ws.cell(row=start_row + idx, column=2, value=str(asin))
        
    wb.save(latest_file)
    print(f"✅ BAŞARILI! {len(asins)} ASIN '{latest_file}' dosyasına işlendi.")
    print("Lütfen bu dosyayı Amazon'daki Upload butonuna basarak doğrudan yükleyin.")

if __name__ == "__main__":
    prepare_amazon_file()
