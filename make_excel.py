import pandas as pd
import json
from datetime import datetime
import logging
import os

# Настройка логирования
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/make_excel.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Путь к папке data
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Путь к файлу для сохранения результатов
OUTPUT_FILE = os.path.join(DATA_DIR, "moex_all_shares.xlsx")

# Ваши данные
data = {
    "securities": {
        "columns": ["SECID", "SHORTNAME", "SECTYPE"], 
        "data": [
            ["ABIO", "iАРТГЕН ао", "1"],
            ["ABRD", "АбрауДюрсо", "1"],
            ["AFKS", "Система ао", "1"],
            ["AFLT", "Аэрофлот", "1"],
            ["AKRN", "Акрон", "1"],
            ["ALRS", "АЛРОСА ао", "1"],
            ["AMEZ", "АшинскийМЗ", "1"],
            ["APRI", "АПРИ", "1"],
            ["APTK", "Аптеки36и6", "1"],
            ["AQUA", "ИНАРКТИКА", "1"],
            ["ARSA", "Арсагера", "1"],
            ["ASSB", "АстрЭнСб", "1"],
            ["ASTR", "iАстра ао", "1"],
            ["AVAN", "Авангрд-ао", "1"],
            ["BANE", "Башнефт ао", "1"],
            ["BANEP", "Башнефт ап", "2"],
            ["BELU", "НоваБев ао", "1"],
            ["BISVP", "БашИнСв ап", "2"],
            ["BLNG", "Белон ао", "1"],
            ["BRZL", "БурЗолото", "1"],
            ["BSPB", "БСП ао", "1"],
            ["BSPBP", "БСП ап", "2"],
            ["CARM", "СТГ", "1"],
            ["CBOM", "МКБ ао", "1"],
            ["CHGZ", "РН-ЗапСиб", "1"],
            ["CHKZ", "ЧКПЗ ао", "1"],
            ["CHMF", "СевСт-ао", "1"],
            ["CHMK", "ЧМК ао", "1"],
            ["CNRU", "Циан", "1"],
            ["CNTL", "Телеграф", "1"],
            ["CNTLP", "Телеграф-п", "2"],
            ["DATA", "iАренадата", "1"],
            ["DELI", "iКаршеринг", "1"],
            ["DIAS", "iДиасофт", "1"],
            ["DIOD", "ЗаводДИОД", "1"],
            ["DOMRF", "ДОМ.РФ", "1"],
            ["DVEC", "ДЭК ао", "1"],
            ["DZRD", "ДонскЗР", "1"],
            ["DZRDP", "ДонскЗР п", "2"],
            ["EELT", "ЕвроЭлтех", "1"],
            ["ELFV", "ЭЛ5Энер ао", "1"],
            ["ELMT", "iЭлемент", "1"],
            ["ENPG", "ЭН+ГРУП ао", "1"],
            ["ETLN", "ЭталонГруп", "1"],
            ["EUTR", "ЕвроТранс", "1"],
            ["FEES", "Россети", "1"],
            ["FESH", "ДВМП ао", "1"],
            ["FIXR", "Фикс Прайс", "1"],
            ["FLOT", "Совкомфлот", "1"],
            ["GAZA", "ГАЗ ао", "1"],
            ["GAZAP", "ГАЗ ап", "2"],
            ["GAZC", "ГАЗКОН-ао", "1"],
            ["GAZP", "ГАЗПРОМ ао", "1"],
            ["GAZS", "ГАЗ-сервис", "1"],
            ["GAZT", "ГАЗ-Тек ао", "1"],
            ["GCHE", "ЧеркизГ-ао", "1"],
            ["GECO", "iГЕНЕТИКО", "1"],
            ["GEMA", "iММЦБ ао", "1"],
            ["GEMC", "МКПАО ЮМГ", "1"],
            ["GLRX", "ГЛОРАКС", "1"],
            ["GMKN", "ГМКНорНик", "1"],
            ["GTRK", "ГТМ ао", "1"],
            ["HEAD", "Хэдхантер", "1"],
            ["HIMCP", "Химпром ап", "2"],
            ["HNFG", "ХЭНДЕРСОН", "1"],
            ["HYDR", "РусГидро", "1"],
            ["IGST", "Ижсталь2ао", "1"],
            ["IGSTP", "Ижсталь ап", "2"],
            ["IRAO", "ИнтерРАОао", "1"],
            ["IRKT", "Яковлев-3", "1"],
            ["IVAT", "iИВА", "1"],
            ["JNOS", "Славн-ЯНОС", "1"],
            ["JNOSP", "Слав-ЯНОСп", "2"],
            ["KAZT", "Куйбазот", "1"],
            ["KAZTP", "Куйбазот-п", "2"],
            ["KBSB", "ТНСэКубань", "1"],
            ["KCHE", "КамчатЭ ао", "1"],
            ["KCHEP", "КамчатЭ ап", "2"],
            ["KFBA", "ИНГРАД ао", "1"],
            ["KGKC", "КурганГКао", "1"],
            ["KGKCP", "КурганГКап", "2"],
            ["KLSB", "КалужскСК", "1"],
            ["KLVZ", "Кристалл", "1"],
            ["KMAZ", "КАМАЗ", "1"],
            ["KMEZ", "КМЗ", "1"],
            ["KOGK", "КоршГОК ао", "1"],
            ["KRKN", "СаратНПЗ", "1"],
            ["KRKNP", "СаратНПЗ-п", "2"],
            ["KRKOP", "ТКЗКК ап", "2"],
            ["KROT", "КрасОкт-ао", "1"],
            ["KROTP", "КрасОкт-1п", "2"],
            ["KRSB", "Красэсб ао", "1"],
            ["KRSBP", "Красэсб ап", "2"],
            ["KUZB", "КузнецкийБ", "1"],
            ["KZOS", "ОргСинт ао", "1"],
            ["KZOSP", "ОргСинт ап", "2"],
            ["LEAS", "Европлан", "1"],
            ["LENT", "Лента ао", "1"],
            ["LIFE", "Фармсинтез", "1"],
            ["LKOH", "ЛУКОЙЛ", "1"],
            ["LMBZ", "Ламбумиз", "1"],
            ["LNZL", "Лензолото", "1"],
            ["LNZLP", "Лензол. ап", "2"],
            ["LPSB", "ЛЭСК ао", "1"],
            ["LSNG", "РСетиЛЭ", "1"],
            ["LSNGP", "РСетиЛЭ-п", "2"],
            ["LSRG", "ЛСР ао", "1"],
            ["LVHK", "Левенгук", "1"],
            ["MAGE", "МагадЭн ао", "1"],
            ["MAGEP", "МагадЭн ап", "2"],
            ["MAGN", "ММК", "1"],
            ["MBNK", "МТС Банк", "1"],
            ["MDMG", "MDMG-ао", "1"],
            ["MFGS", "Мегион-ао", "1"],
            ["MFGSP", "Мегион-ап", "2"],
            ["MGKL", "МГКЛ", "1"],
            ["MGNT", "Магнит ао", "1"],
            ["MGNZ", "СМЗ-ао", "1"],
            ["MGTS", "МГТС-5ао", "1"],
            ["MGTSP", "МГТС-4ап", "2"],
            ["MISB", "ТНСэнМарЭл", "1"],
            ["MISBP", "ТНСэМаЭл-п", "2"],
            ["MOEX", "МосБиржа", "1"],
            ["MRKC", "РоссЦентр", "1"],
            ["MRKK", "Россети СК", "1"],
            ["MRKP", "РСетиЦП ао", "1"],
            ["MRKS", "РсетСиб ао", "1"],
            ["MRKU", "Россети Ур", "1"],
            ["MRKV", "РсетВол ао", "1"],
            ["MRKY", "РоссЮг ао", "1"],
            ["MRKZ", "РСетиСЗ ао", "1"],
            ["MRSB", "МордЭнСб", "1"],
            ["MSNG", "+МосЭнерго", "1"],
            ["MSRS", "РСетиМР ао", "1"],
            ["MSTT", "Мостотрест", "1"],
            ["MTLR", "Мечел ао", "1"],
            ["MTLRP", "Мечел ап", "2"],
            ["MTSS", "МТС-ао", "1"],
            ["MVID", "М.видео", "1"],
            ["NAUK", "iНПОНаука", "1"],
            ["NFAZ", "НЕФАЗ", "1"],
            ["NKHP", "НКХП ао", "1"],
            ["NKNC", "НКНХ ао", "1"],
            ["NKNCP", "НКНХ ап", "2"],
            ["NKSH", "Нижкамшина", "1"],
            ["NLMK", "НЛМК ао", "1"],
            ["NMTP", "НМТП ао", "1"],
            ["NNSB", "ТНСэнНН ао", "1"],
            ["NNSBP", "ТНСэнНН ап", "2"],
            ["NSVZ", "iНаукаСвяз", "1"],
            ["NVTK", "Новатэк ао", "1"],
            ["OGKB", "ОГК-2 ао", "1"],
            ["OKEY", "OKEY-гдр", "D"],
            ["OMZZP", "ОМЗ-ап", "2"],
            ["OZON", "Озон", "1"],
            ["OZPH", "iОзонФарм", "1"],
            ["PAZA", "ПавлАвт ао", "1"],
            ["PHOR", "ФосАгро ао", "1"],
            ["PIKK", "ПИК ао", "1"],
            ["PLZL", "Полюс", "1"],
            ["PMSB", "ПермьЭнСб", "1"],
            ["PMSBP", "ПермьЭнС-п", "2"],
            ["POSI", "iПозитив", "1"],
            ["PRFN", "ТЕПЛАНТ ао", "1"],
            ["PRMB", "Приморье", "1"],
            ["PRMD", "iПРОМОМЕД", "1"],
            ["RAGR", "Русагро", "1"],
            ["RASP", "Распадская", "1"],
            ["RBCM", "ГК РБК ао", "1"],
            ["RDRB", "РДБанк ао", "1"],
            ["RENI", "Ренессанс", "1"],
            ["RGSS", "РГС СК ао", "1"],
            ["RKKE", "ЭнергияРКК", "1"],
            ["RNFT", "РуссНфт ао", "1"],
            ["ROLO", "Русолово", "1"],
            ["ROSN", "Роснефть", "1"],
            ["ROST", "РОСИНТЕРао", "1"],
            ["RTGZ", "ГР Ростов", "1"],
            ["RTKM", "Ростел -ао", "1"],
            ["RTKMP", "Ростел -ап", "2"],
            ["RTSB", "ТНСэнРст", "1"],
            ["RTSBP", "ТНСэнРст-п", "2"],
            ["RUAL", "РУСАЛ ао", "1"],
            ["RUSI", "ИКРУСС-ИНВ", "1"],
            ["RZSB", "РязЭнСб", "1"],
            ["SAGO", "СамарЭн-ао", "1"],
            ["SAGOP", "СамарЭн-ап", "2"],
            ["SARE", "СаратЭн-ао", "1"],
            ["SAREP", "СаратЭн-ап", "2"],
            ["SBER", "Сбербанк", "1"],
            ["SBERP", "Сбербанк-п", "2"],
            ["SELG", "Селигдар", "1"],
            ["SFIN", "ЭсЭфАй ао", "1"],
            ["SGZH", "Сегежа", "1"],
            ["SIBN", "Газпрнефть", "1"],
            ["SLEN", "Сахэнер ао", "1"],
            ["SMLT", "Самолет ао", "1"],
            ["SNGS", "Сургнфгз", "1"],
            ["SNGSP", "Сургнфгз-п", "2"],
            ["SOFL", "iСофтлайн", "1"],
            ["SPBE", "СПБ Биржа", "1"],
            ["STSB", "СтаврЭнСб", "1"],
            ["STSBP", "СтаврЭнСбп", "2"],
            ["SVAV", "СОЛЛЕРС", "1"],
            ["SVCB", "Совкомбанк", "1"],
            ["SVET", "Светофор", "1"],
            ["SVETP", "Светофор п", "2"],
            ["T", "Т-Техно ао", "1"],
            ["TASB", "ТамбЭнСб", "1"],
            ["TASBP", "ТамбЭнСб-п", "2"],
            ["TATN", "Татнфт 3ао", "1"],
            ["TATNP", "Татнфт 3ап", "2"],
            ["TGKA", "ТГК-1", "1"],
            ["TGKB", "ТГК-2", "1"],
            ["TGKBP", "ТГК-2 ап", "2"],
            ["TGKN", "ТГК-14", "1"],
            ["TNSE", "ТНСэнрг ао", "1"],
            ["TORS", "РСТомск ао", "1"],
            ["TORSP", "РСТомск ап", "2"],
            ["TRMK", "ТМК ао", "1"],
            ["TRNFP", "Транснф ап", "2"],
            ["TTLK", "Таттел. ао", "1"],
            ["TUZA", "ТЗА ао", "1"],
            ["UGLD", "ЮГК", "1"],
            ["UKUZ", "ЮжКузб. ао", "1"],
            ["UNAC", "iАвиастКао", "1"],
            ["UNKL", "ЮУНК ао", "1"],
            ["UPRO", "Юнипро ао", "1"],
            ["URKZ", "УрКузница", "1"],
            ["USBN", "УралСиб ао", "1"],
            ["UTAR", "ЮТэйр ао", "1"],
            ["UWGN", "ОВК ао", "1"],
            ["VEON-RX", "VEON", "1"],
            ["VGSB", "ВолгЭнСб", "1"],
            ["VGSBP", "ВолгЭнСб-п", "2"],
            ["VJGZ", "Варьеган", "1"],
            ["VJGZP", "Варьеган-п", "2"],
            ["VKCO", "МКПАО \"ВК\"", "1"],
            ["VLHZ", "ВХЗ-ао", "1"],
            ["VRSB", "ТНСэнВорон", "1"],
            ["VRSBP", "ТНСэнВор-п", "2"],
            ["VSEH", "ВИ.ру", "1"],
            ["VSMO", "ВСМПО-АВСМ", "1"],
            ["VSYD", "ВыбСудЗ ао", "1"],
            ["VSYDP", "ВыбСудЗ ап", "2"],
            ["VTBR", "ВТБ ао", "1"],
            ["WTCM", "ЦМТ ао", "1"],
            ["WTCMP", "ЦМТ ап", "2"],
            ["WUSH", "iВУШХолднг", "1"],
            ["X5", "КЦ ИКС 5", "1"],
            ["YAKG", "ЯТЭК ао", "1"],
            ["YDEX", "ЯНДЕКС", "1"],
            ["YKEN", "Якутскэнрг", "1"],
            ["YKENP", "Якутскэн-п", "2"],
            ["YRSB", "ТНСэнЯр", "1"],
            ["YRSBP", "ТНСэнЯр-п", "2"],
            ["ZAYM", "Займер ао", "1"],
            ["ZILL", "ЗИЛ ао", "1"],
            ["ZVEZ", "ЗВЕЗДА ао", "1"]
        ]
    }
}

def create_excel_from_data():
    """
    Создает Excel-файл из предоставленных данных
    """
    logger.info("Начинаем создание Excel-файла...")
    
    try:
        # Извлекаем данные из JSON
        columns = data["securities"]["columns"]
        securities_data = data["securities"]["data"]
        
        logger.info(f"Получено {len(securities_data)} инструментов")
        
        # Создаем DataFrame
        df = pd.DataFrame(securities_data, columns=columns)
        
        # Переименовываем колонки на русский
        df = df.rename(columns={
            "SECID": "Тикер",
            "SHORTNAME": "Название",
            "SECTYPE": "Тип_акции"
        })
        
        # Добавляем расшифровку типа акции
        def get_type_description(sectype):
            if sectype == "1":
                return "Обыкновенная акция"
            elif sectype == "2":
                return "Привилегированная акция"
            elif sectype == "D":
                return "Депозитарная расписка"
            else:
                return f"Неизвестный тип ({sectype})"
        
        df["Тип_акции_расшифровка"] = df["Тип_акции"].apply(get_type_description)
        
        # Добавляем информацию о количестве
        total_count = len(df)
        common_count = len(df[df["Тип_акции"] == "1"])
        preferred_count = len(df[df["Тип_акции"] == "2"])
        dr_count = len(df[df["Тип_акции"] == "D"])
        
        logger.info(f"Всего инструментов: {total_count}")
        logger.info(f"Обыкновенных акций: {common_count}")
        logger.info(f"Привилегированных акций: {preferred_count}")
        logger.info(f"Депозитарных расписок: {dr_count}")
        
        # Сортируем по тикеру
        df = df.sort_values(by="Тикер").reset_index(drop=True)
        
        # Добавляем номер строки
        df.insert(0, "№", range(1, len(df) + 1))
        
        # Сохраняем в Excel
        with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
            # Основной лист со всеми акциями
            df.to_excel(writer, sheet_name='Все акции', index=False)
            
            # Лист только с обыкновенными акциями
            common_shares = df[df["Тип_акции"] == "1"].copy()
            common_shares.to_excel(writer, sheet_name='Обыкновенные акции', index=False)
            
            # Лист только с привилегированными акциями
            preferred_shares = df[df["Тип_акции"] == "2"].copy()
            preferred_shares.to_excel(writer, sheet_name='Привилегированные акции', index=False)
            
            # Лист со сводной информацией
            summary_data = {
                "Категория": ["Всего инструментов", "Обыкновенные акции", "Привилегированные акции", "Депозитарные расписки"],
                "Количество": [total_count, common_count, preferred_count, dr_count],
                "Процент": [
                    f"100%",
                    f"{common_count/total_count*100:.1f}%",
                    f"{preferred_count/total_count*100:.1f}%",
                    f"{dr_count/total_count*100:.1f}%"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Сводка', index=False)
            
            # Настраиваем ширину колонок для каждого листа
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                
                if sheet_name == 'Все акции':
                    for idx, col in enumerate(df.columns, 1):
                        column_width = max(
                            df[col].astype(str).apply(len).max(),
                            len(str(col))
                        ) + 2
                        worksheet.column_dimensions[chr(64 + idx)].width = min(column_width, 50)
                
                elif sheet_name == 'Обыкновенные акции':
                    for idx, col in enumerate(common_shares.columns, 1):
                        column_width = max(
                            common_shares[col].astype(str).apply(len).max(),
                            len(str(col))
                        ) + 2
                        worksheet.column_dimensions[chr(64 + idx)].width = min(column_width, 50)
                
                elif sheet_name == 'Привилегированные акции':
                    for idx, col in enumerate(preferred_shares.columns, 1):
                        column_width = max(
                            preferred_shares[col].astype(str).apply(len).max(),
                            len(str(col))
                        ) + 2
                        worksheet.column_dimensions[chr(64 + idx)].width = min(column_width, 50)
                
                elif sheet_name == 'Сводка':
                    for idx, col in enumerate(summary_df.columns, 1):
                        column_width = max(
                            summary_df[col].astype(str).apply(len).max(),
                            len(str(col))
                        ) + 2
                        worksheet.column_dimensions[chr(64 + idx)].width = min(column_width, 30)
        
        logger.info(f"Файл успешно сохранен: {OUTPUT_FILE}")
        
        # Выводим статистику
        print(f"✅ Успешно создан файл: {OUTPUT_FILE}")
        print(f"📊 Статистика:")
        print(f"   Всего инструментов: {total_count}")
        print(f"   Обыкновенные акции: {common_count}")
        print(f"   Привилегированные акции: {preferred_count}")
        print(f"   Депозитарные расписки: {dr_count}")
        print(f"\n📑 Листы в файле:")
        print(f"   1. 'Все акции' - все {total_count} инструментов")
        print(f"   2. 'Обыкновенные акции' - {common_count} акций")
        print(f"   3. 'Привилегированные акции' - {preferred_count} акций")
        print(f"   4. 'Сводка' - статистика по типам инструментов")
        
        # Сохраняем также в CSV для удобства
        csv_file = OUTPUT_FILE.replace('.xlsx', '.csv')
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        print(f"\n💾 Данные также сохранены в CSV: {csv_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при создании Excel-файла: {e}")
        print(f"❌ Ошибка: {e}")
        return False

def main():
    """
    Основная функция
    """
    print("📊 Создание Excel-файла с акциями MOEX...")
    print("=" * 50)
    
    success = create_excel_from_data()
    
    if success:
        print("=" * 50)
        print("🎉 Файл успешно создан!")
    else:
        print("=" * 50)
        print("😞 Произошла ошибка при создании файла")

if __name__ == "__main__":
    main()