"""
Генератор отчетов с улучшенным форматированием
"""

import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict
from colorama import Fore, Style, Back
import openpyxl
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule

from .core.config import Config

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Генератор отчетов в различных форматах с улучшенным форматированием"""
    
    def __init__(self, results: List[Dict], params: Dict):
        """
        Args:
            results: Результаты анализа
            params: Параметры анализа
        """
        self.results = results
        self.params = params
        
        # Создаем директории
        Config.ensure_directories()
        
        # Таймстамп для имен файлов
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Стили для Excel
        self._setup_excel_styles()
    
    def _setup_excel_styles(self):
        """Настраивает стили для Excel отчета"""
        # Основные цвета
        self.colors = {
            'header_bg': '2E75B6',  # Синий
            'header_fg': 'FFFFFF',  # Белый
            'positive': 'C6EFCE',   # Зеленый
            'positive_text': '006100', # Темно-зеленый
            'negative': 'FFC7CE',   # Красный
            'negative_text': '9C0006', # Темно-красный
            'neutral': 'FFEB9C',    # Желтый
            'neutral_text': '9C5700', # Темно-желтый
            'row_light': 'F8F9FA',  # Светло-серый
            'row_dark': 'E9ECEF',   # Темно-серый
            'border': 'A5A5A5',     # Серый
        }
        
        # Шрифты
        self.fonts = {
            'header': Font(name='Calibri', size=11, bold=True, color=self.colors['header_fg']),
            'normal': Font(name='Calibri', size=10),
            'bold': Font(name='Calibri', size=10, bold=True),
            'small': Font(name='Calibri', size=9),
        }
        
        # Границы
        thin_border = Side(border_style="thin", color=self.colors['border'])
        thick_border = Side(border_style="thick", color=self.colors['border'])
        self.border = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
        self.thick_border = Border(left=thick_border, right=thick_border, top=thick_border, bottom=thick_border)
        
        # Выравнивание
        self.align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        self.align_left = Alignment(horizontal='left', vertical='center', wrap_text=True)
        self.align_right = Alignment(horizontal='right', vertical='center')
        
        # Заливки
        self.fills = {
            'header': PatternFill(start_color=self.colors['header_bg'], 
                                  end_color=self.colors['header_bg'], 
                                  fill_type="solid"),
            'positive': PatternFill(start_color=self.colors['positive'], 
                                    end_color=self.colors['positive'], 
                                    fill_type="solid"),
            'negative': PatternFill(start_color=self.colors['negative'], 
                                    end_color=self.colors['negative'], 
                                    fill_type="solid"),
            'neutral': PatternFill(start_color=self.colors['neutral'], 
                                   end_color=self.colors['neutral'], 
                                   fill_type="solid"),
            'row_light': PatternFill(start_color=self.colors['row_light'], 
                                     end_color=self.colors['row_light'], 
                                     fill_type="solid"),
            'row_dark': PatternFill(start_color=self.colors['row_dark'], 
                                    end_color=self.colors['row_dark'], 
                                    fill_type="solid"),
        }
    
    def generate_excel_report(self) -> str:
        """Генерирует Excel отчет с улучшенным форматированием"""
        try:
            if not self.results:
                print(Fore.YELLOW + "⚠️  Нет данных для отчета")
                return ""
            
            # Имя файла
            filename = f"moex_analysis_{self.timestamp}.xlsx"
            filepath = os.path.join(Config.REPORTS_DIR, filename)
            
            # Создаем новую рабочую книгу
            wb = openpyxl.Workbook()
            
            # Основной лист с данными
            ws_main = wb.active
            ws_main.title = "Топ акции"
            
            # Создаем данные для таблицы
            headers = ['№', 'Тикер', 'Название', 'Тип акции', 'Текущая цена', 
                      'Дней данных']
            
            # Добавляем колонки для прогнозов по дням
            for day_idx, day in enumerate(self.params['prediction_days']):
                headers.extend([
                    f'Цена через {day} дн.',
                    f'Изменение {day} дн. %',
                    f'Уверенность {day} дн. %'
                ])
            
            # Добавляем заголовки
            for col_idx, header in enumerate(headers, 1):
                cell = ws_main.cell(row=1, column=col_idx, value=header)
                cell.font = self.fonts['header']
                cell.fill = self.fills['header']
                cell.alignment = self.align_center
                cell.border = self.border
            
            # Устанавливаем высоту первой строки
            ws_main.row_dimensions[1].height = 36
            
            # Заполняем данные
            for row_idx, result in enumerate(self.results, 2):
                # Определяем цвет строки (чередование)
                row_fill = self.fills['row_light'] if row_idx % 2 == 0 else self.fills['row_dark']
                
                # Основные данные
                data = [
                    row_idx - 1,  # №
                    result['ticker'],
                    result['name'][:40],
                    result.get('type_description', ''),
                    f"{result['last_price']:.2f}",
                    result['data_points'],
                ]
                
                # Прогнозы по дням
                for day in self.params['prediction_days']:
                    pred_key = f'day_{day}'
                    if pred_key in result['predictions']:
                        pred = result['predictions'][pred_key]
                        pred_date = (datetime.now() + timedelta(days=day)).strftime('%d.%m.%Y')
                        
                        data.extend([
                            f"{pred.get('price', 0):.2f}",
                            f"{pred.get('change_percent', 0):+.2f}",
                            f"{pred.get('confidence', 0)*100:.1f}"
                        ])
                    else:
                        data.extend(['-', '-', '-'])
                
                # Записываем данные
                for col_idx, value in enumerate(data, 1):
                    cell = ws_main.cell(row=row_idx, column=col_idx, value=value)
                    cell.font = self.fonts['normal']
                    cell.fill = row_fill
                    cell.border = self.border
                    
                    # Выравнивание в зависимости от типа данных
                    if col_idx in [1, 5]:  # Номер, цена
                        cell.alignment = self.align_right
                    elif col_idx in [2, 3, 4]:  # Тикер, название, тип
                        cell.alignment = self.align_left
                    else:  # Процентные значения и дни
                        cell.alignment = self.align_right
                    
                    # Цвет текста для процентных изменений
                    header_text = ws_main.cell(row=1, column=col_idx).value
                    if 'Изменение' in str(header_text):
                        try:
                            change_value = float(str(value).replace('%', '').replace('+', ''))
                            if change_value > 0:
                                cell.font = Font(name='Calibri', size=10, color=self.colors['positive_text'])
                            elif change_value < 0:
                                cell.font = Font(name='Calibri', size=10, color=self.colors['negative_text'])
                        except:
                            pass
            
            # Настройка ширины колонок
            for col_idx in range(1, len(headers) + 1):
                column_letter = get_column_letter(col_idx)
                
                # Устанавливаем ширину 13 для колонок после "дней данных" (т.е. после 6-й колонки)
                if col_idx > 6:
                    ws_main.column_dimensions[column_letter].width = 13
                else:
                    # Для первых колонок устанавливаем ширину по содержимому, но не менее 10
                    max_length = 0
                    for row in range(1, len(self.results) + 2):  # +2 чтобы включить заголовок и одну строку данных
                        cell = ws_main.cell(row=row, column=col_idx)
                        length = len(str(cell.value)) if cell.value else 0
                        if length > max_length:
                            max_length = length
                    ws_main.column_dimensions[column_letter].width = min(max(10, max_length + 2), 30)
            
            # Добавляем жирные границы между периодами прогноза
            # Колонки с прогнозами начинаются с 7-й (индекс 6), идут по 3 на каждый период
            if len(self.params['prediction_days']) > 1:
                # Индекс начала первой группы прогнозных колонок (Цена через N дней)
                start_of_forecasts = 7
                for i, day in enumerate(self.params['prediction_days']):
                    # Индекс последней колонки текущего периода (Уверенность N дн. %)
                    end_of_current_period = start_of_forecasts + (i * 3) + 2
                    
                    # Добавляем жирную границу справа от последней колонки текущего периода
                    # (если это не последний период)
                    if i < len(self.params['prediction_days']) - 1:
                        for row_idx in range(1, len(self.results) + 2):
                            cell = ws_main.cell(row=row_idx, column=end_of_current_period)
                            # Сохраняем текущие стили и добавляем жирную правую границу
                            current_border = cell.border
                            cell.border = Border(
                                left=current_border.left,
                                right=self.thick_border.right,  # Жирная правая граница
                                top=current_border.top,
                                bottom=current_border.bottom
                            )
            
            # Добавляем условное форматирование
            self._add_conditional_formatting(ws_main)
            
            # Лист со сводкой
            ws_summary = wb.create_sheet("Сводка")
            self._add_summary_sheet(ws_summary)
            
            # Лист с деталями моделей (для глубокого режима)
            if self.params['mode'] == 3 and any('individual_predictions' in r.get('predictions', {}).get(f'day_{day}', {}) 
                                              for r in self.results for day in self.params['prediction_days']):
                ws_models = wb.create_sheet("Детали моделей")
                self._add_models_sheet(ws_models)
            
            # Лист с графиками
            ws_charts = wb.create_sheet("Графики")
            self._add_charts_sheet(ws_charts)
            
            # Сохраняем файл
            wb.save(filepath)
            
            print(Fore.GREEN + f"✅ Excel отчет сохранен: {filepath}")
            return filepath
            
        except Exception as e:
            print(Fore.RED + f"❌ Ошибка создания Excel отчета: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _build_dataframe(self) -> pd.DataFrame:
        """Собирает плоский DataFrame из результатов анализа (для CSV/JSON)."""
        rows = []
        for i, r in enumerate(self.results, 1):
            row = {
                '№': i,
                'Тикер': r.get('ticker', ''),
                'Название': r.get('name', ''),
                'Тип акции': r.get('type_description', ''),
                'Текущая цена': r.get('last_price', 0),
                'Средний рост %': r.get('avg_change_percent', 0),
                'Средняя уверенность %': round(r.get('avg_confidence', 0) * 100, 1),
                'Дней данных': r.get('data_points', r.get('days', '')),
            }
            for day in self.params.get('prediction_days', []):
                pred = (r.get('predictions') or {}).get(day) or {}
                row[f'Цена через {day} дн.'] = pred.get('price', '')
                row[f'Изменение {day} дн. %'] = pred.get('change_percent', '')
                row[f'Уверенность {day} дн. %'] = round(pred.get('confidence', 0) * 100, 1) if pred else ''
            rows.append(row)
        return pd.DataFrame(rows)

    def generate_csv_report(self) -> str:
        """Генерирует CSV отчет (плоская таблица результатов анализа)."""
        try:
            if not self.results:
                print(Fore.YELLOW + "⚠️  Нет данных для отчета")
                return ""

            Config.ensure_directories()
            filename = f"moex_analysis_{self.timestamp}.csv"
            filepath = os.path.join(Config.REPORTS_DIR, filename)

            df = self._build_dataframe()
            # utf-8-sig — чтобы файл корректно открывался в Excel
            df.to_csv(filepath, index=False, encoding='utf-8-sig')

            logger.info(f"CSV отчет сохранен: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Ошибка генерации CSV отчета: {e}", exc_info=True)
            print(Fore.RED + f"❌ Ошибка генерации CSV отчета: {e}")
            return ""

    def generate_json_report(self) -> str:
        """Генерирует JSON отчет (полные результаты + параметры анализа)."""
        try:
            if not self.results:
                print(Fore.YELLOW + "⚠️  Нет данных для отчета")
                return ""

            Config.ensure_directories()
            filename = f"moex_analysis_{self.timestamp}.json"
            filepath = os.path.join(Config.REPORTS_DIR, filename)

            payload = {
                'generated_at': datetime.now().isoformat(timespec='seconds'),
                'params': {
                    **{k: v for k, v in self.params.items()},
                    'prediction_days': list(self.params.get('prediction_days', [])),
                },
                'results': self.results,
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

            logger.info(f"JSON отчет сохранен: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Ошибка генерации JSON отчета: {e}", exc_info=True)
            print(Fore.RED + f"❌ Ошибка генерации JSON отчета: {e}")
            return ""

    def _add_conditional_formatting(self, ws):
        """Добавляет условное форматирование"""
        # Форматирование для колонки с прогнозом роста
        last_col = ws.max_column
        
        # Находим колонки с процентными изменениями
        for col in range(1, last_col + 1):
            header = ws.cell(row=1, column=col).value
            if header and 'Изменение' in str(header):
                # Зеленый для положительных значений
                positive_rule = FormulaRule(formula=[f'AND(ISNUMBER({get_column_letter(col)}2), {get_column_letter(col)}2>0)'],
                                          fill=self.fills['positive'])
                
                # Красный для отрицательных значений
                negative_rule = FormulaRule(formula=[f'AND(ISNUMBER({get_column_letter(col)}2), {get_column_letter(col)}2<0)'],
                                          fill=self.fills['negative'])
                
                ws.conditional_formatting.add(f'{get_column_letter(col)}2:{get_column_letter(col)}{ws.max_row}', positive_rule)
                ws.conditional_formatting.add(f'{get_column_letter(col)}2:{get_column_letter(col)}{ws.max_row}', negative_rule)
    
    def _add_summary_sheet(self, ws):
        """Добавляет лист со сводкой"""
        # Заголовок
        ws.merge_cells('A1:B1')
        title_cell = ws['A1']
        title_cell.value = "📊 СВОДКА АНАЛИЗА АКЦИЙ MOEX"
        title_cell.font = Font(name='Calibri', size=16, bold=True, color=self.colors['header_bg'])
        title_cell.alignment = self.align_center
        
        # Основная информация
        summary_data = [
            ["Дата анализа:", datetime.now().strftime('%d.%m.%Y %H:%M:%S')],
            ["Тип акций:", Config.STOCK_TYPES.get(self.params['stock_type'], 'Неизвестный')],
            ["Режим анализа:", Config.MODES.get(self.params['mode'], {}).get('name', 'Неизвестный')],
            ["Дни прогноза:", ', '.join(map(str, self.params['prediction_days']))],
            ["Минимальная уверенность:", f"{self.params['min_confidence']*100:.0f}%"],
            ["Всего проанализировано:", f"{len(self.results)} тикеров"],
            ["", ""],
            ["ЛУЧШИЕ РЕЗУЛЬТАТЫ", ""],
        ]
        
        if self.results:
            summary_data.extend([
                ["Лучший тикер:", self.results[0]['ticker']],
                ["Лучший рост:", f"{self.results[0]['avg_change_percent']:+.2f}%"],
                ["Уверенность:", f"{self.results[0]['avg_confidence']*100:.1f}%"],
                ["", ""],
                ["СТАТИСТИКА", ""],
                ["Средний рост:", f"{np.mean([r['avg_change_percent'] for r in self.results]):+.2f}%"],
                ["Средняя уверенность:", f"{np.mean([r['avg_confidence'] for r in self.results])*100:.1f}%"],
                ["Положительных прогнозов:", f"{sum(1 for r in self.results if r['avg_change_percent'] > 0)}"],
                ["Отрицательных прогнозов:", f"{sum(1 for r in self.results if r['avg_change_percent'] < 0)}"],
            ])
        
        # Заполняем данные
        for row_idx, (label, value) in enumerate(summary_data, 3):
            # Метка
            label_cell = ws.cell(row=row_idx, column=1, value=label)
            label_cell.font = self.fonts['bold']
            label_cell.alignment = self.align_left
            label_cell.border = self.border
            
            # Значение
            value_cell = ws.cell(row=row_idx, column=2, value=value)
            
            # Стиль для заголовков разделов
            if label in ["ЛУЧШИЕ РЕЗУЛЬТАТЫ", "СТАТИСТИКА"]:
                value_cell.value = ""  # Пустое значение для выравнивания
                ws.merge_cells(f'A{row_idx}:B{row_idx}')
                label_cell.fill = PatternFill(start_color='E2EFDA', end_color='E2EFDA', fill_type="solid")
                label_cell.font = Font(name='Calibri', size=12, bold=True)
                label_cell.alignment = self.align_center
            else:
                value_cell.font = self.fonts['normal']
                value_cell.alignment = self.align_left
                value_cell.border = self.border
                
                # Цвет для процентных значений
                if '%' in str(value) and '+' in str(value):
                    value_cell.font = Font(name='Calibri', size=10, bold=True, color=self.colors['positive_text'])
                elif '%' in str(value) and '-' in str(value):
                    value_cell.font = Font(name='Calibri', size=10, bold=True, color=self.colors['negative_text'])
        
        # Настройка ширины колонок
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 30
        
        # Добавляем итоговую строку
        last_row = len(summary_data) + 3
        ws.merge_cells(f'A{last_row}:B{last_row}')
        final_cell = ws.cell(row=last_row, column=1)
        final_cell.value = "🎉 Анализ успешно завершен!"
        final_cell.font = Font(name='Calibri', size=12, bold=True, color=self.colors['header_bg'])
        final_cell.alignment = self.align_center
        final_cell.fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type="solid")
    
    def _add_models_sheet(self, ws):
        """Добавляет лист с деталями по моделям"""
        headers = ['Тикер', 'День', 'Модель', 'Цена', 'Изменение %', 'Уверенность %']
        
        # Заголовки
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = self.fonts['header']
            cell.fill = self.fills['header']
            cell.alignment = self.align_center
            cell.border = self.border
        
        row_idx = 2
        for result in self.results:
            for day in self.params['prediction_days']:
                pred_key = f'day_{day}'
                if pred_key in result['predictions']:
                    pred = result['predictions'][pred_key]
                    if 'individual_predictions' in pred:
                        for model_pred in pred['individual_predictions']:
                            # Определяем цвет строки
                            row_fill = self.fills['row_light'] if row_idx % 2 == 0 else self.fills['row_dark']
                            
                            data = [
                                result['ticker'],
                                day,
                                model_pred.get('model', 'unknown'),
                                f"{model_pred.get('price', 0):.2f}",
                                f"{model_pred.get('change_percent', 0):+.2f}",
                                f"{model_pred.get('confidence', 0)*100:.1f}"
                            ]
                            
                            for col_idx, value in enumerate(data, 1):
                                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                                cell.font = self.fonts['normal']
                                cell.fill = row_fill
                                cell.border = self.border
                                cell.alignment = self.align_center if col_idx in [2, 4, 5, 6] else self.align_left
                            
                            row_idx += 1
        
        # Настройка ширины
        for col_idx in range(1, len(headers) + 1):
            column_letter = get_column_letter(col_idx)
            ws.column_dimensions[column_letter].width = 13
    
    def _add_charts_sheet(self, ws_charts):
        """Добавляет лист с графиками (заглушка для будущего расширения)"""
        ws_charts['A1'] = "📈 ГРАФИКИ И ВИЗУАЛИЗАЦИИ"
        ws_charts['A1'].font = Font(name='Calibri', size=14, bold=True, color=self.colors['header_bg'])
        
        ws_charts['A3'] = "Здесь будут графики распределения прогнозов"
        ws_charts['A5'] = "и другие визуализации в будущих версиях"
        
        ws_charts.column_dimensions['A'].width = 40
    
    def print_console_report(self):
        """Выводит красивый отчет в консоль"""
        if not self.results:
            print(Fore.YELLOW + "⚠️  Нет данных для отчета")
            return
        
        # Верхняя граница с заголовком
        print(Fore.CYAN + "╔" + "═" * 78 + "╗")
        print(Fore.CYAN + "║" + Fore.YELLOW + " " * 78 + Fore.CYAN + "║")
        print(Fore.CYAN + "║" + Fore.YELLOW + " " * 30 + "📊 ОТЧЕТ ОБ АНАЛИЗЕ АКЦИЙ MOEX" + " " * 20 + Fore.CYAN + "║")
        print(Fore.CYAN + "║" + Fore.YELLOW + " " * 78 + Fore.CYAN + "║")
        print(Fore.CYAN + "╠" + "═" * 78 + "╣")
        
        # Топ-10 акций
        top_count = min(10, len(self.results))
        
        print(Fore.CYAN + "║" + Fore.WHITE + " " * 20 + f"🏆 ТОП-{top_count} АКЦИЙ ПО ПРОГНОЗИРУЕМОМУ РОСТУ" + " " * 20 + Fore.CYAN + "║")
        print(Fore.CYAN + "╠" + "─" * 78 + "╣")
        
        for i, result in enumerate(self.results[:top_count], 1):
            # Эмодзи для мест
            if i == 1:
                emoji = "🥇"
                place_color = Fore.YELLOW
            elif i == 2:
                emoji = "🥈"
                place_color = Fore.LIGHTBLACK_EX
            elif i == 3:
                emoji = "🥉"
                place_color = Fore.MAGENTA
            else:
                emoji = f"{i}."
                place_color = Fore.WHITE
            
            # Цвет для роста
            growth = result['avg_change_percent']
            if growth > 10:
                growth_color = Fore.GREEN + Style.BRIGHT
                growth_symbol = "📈🚀"
            elif growth > 5:
                growth_color = Fore.GREEN
                growth_symbol = "📈"
            elif growth > 0:
                growth_color = Fore.CYAN
                growth_symbol = "↗️"
            elif growth < -10:
                growth_color = Fore.RED + Style.BRIGHT
                growth_symbol = "📉💥"
            elif growth < -5:
                growth_color = Fore.RED
                growth_symbol = "📉"
            else:
                growth_color = Fore.YELLOW
                growth_symbol = "➡️"
            
            # Форматирование строки
            name_display = result['name'][:25] + "..." if len(result['name']) > 25 else result['name']
            
            print(Fore.CYAN + "║ " + place_color + f"{emoji:3s} " + Fore.WHITE + f"{result['ticker']:6s} " + 
                  Fore.CYAN + f"{name_display:28s}" + Fore.WHITE + " | " + 
                  growth_color + f"{growth_symbol} {growth:+.2f}%" + Fore.WHITE + " | " + 
                  Fore.CYAN + f"Уверенность: {result['avg_confidence']*100:.1f}%" + " " * 5 + Fore.CYAN + "║")
            
            # Дополнительная информация
            if i < top_count:  # Не для последней строки
                print(Fore.CYAN + "║" + " " * 78 + "║")
        
        print(Fore.CYAN + "╠" + "═" * 78 + "╣")
        
        # Статистика
        print(Fore.CYAN + "║" + Fore.WHITE + " " * 30 + "📈 СТАТИСТИКА АНАЛИЗА" + " " * 27 + Fore.CYAN + "║")
        print(Fore.CYAN + "╠" + "─" * 78 + "╣")
        
        # Рассчитываем статистику
        avg_growth = np.mean([r['avg_change_percent'] for r in self.results])
        avg_confidence = np.mean([r['avg_confidence'] for r in self.results]) * 100
        median_growth = np.median([r['avg_change_percent'] for r in self.results])
        positive = sum(1 for r in self.results if r['avg_change_percent'] > 0)
        negative = sum(1 for r in self.results if r['avg_change_percent'] < 0)
        neutral = sum(1 for r in self.results if r['avg_change_percent'] == 0)
        
        # Цвет для средней статистики
        avg_growth_color = Fore.GREEN if avg_growth > 0 else Fore.RED if avg_growth < 0 else Fore.YELLOW
        
        print(Fore.CYAN + "║ " + Fore.WHITE + f"📊 Всего акций: {Fore.CYAN}{len(self.results):4d}" + 
              " " * 10 + Fore.WHITE + f"📈 Средний рост: {avg_growth_color}{avg_growth:+.2f}%" + " " * 10 + Fore.CYAN + "║")
        
        print(Fore.CYAN + "║ " + Fore.WHITE + f"🎯 Средняя уверенность: {Fore.CYAN}{avg_confidence:.1f}%" + 
              " " * 10 + Fore.WHITE + f"📊 Медианный рост: {Fore.CYAN}{median_growth:+.2f}%" + " " * 5 + Fore.CYAN + "║")
        
        print(Fore.CYAN + "║ " + Fore.WHITE + f"📈 Положительных прогнозов: {Fore.GREEN}{positive:3d}" + 
              " " * 8 + Fore.WHITE + f"📉 Отрицательных прогнозов: {Fore.RED}{negative:3d}" + " " * 5 + Fore.CYAN + "║")
        
        print(Fore.CYAN + "║ " + Fore.WHITE + f"📅 Дата анализа: {Fore.CYAN}{datetime.now().strftime('%d.%m.%Y %H:%M')}" + 
              " " * 15 + Fore.WHITE + f"🎯 Минимальная уверенность: {Fore.CYAN}{self.params['min_confidence']*100:.0f}%" + Fore.CYAN + "║")
        
        # Лучшие и худшие
        if len(self.results) >= 3:
            print(Fore.CYAN + "╠" + "─" * 78 + "╣")
            print(Fore.CYAN + "║" + Fore.WHITE + " " * 30 + "🏅 ЛУЧШИЕ И ХУДШИЕ" + " " * 30 + Fore.CYAN + "║")
            print(Fore.CYAN + "╠" + "─" * 78 + "╣")
            
            best = self.results[0]
            worst = self.results[-1]
            
            print(Fore.CYAN + "║ " + Fore.GREEN + f"🥇 Лучшая: {best['ticker']} ({best['avg_change_percent']:+.2f}%)" + 
                  " " * 15 + Fore.RED + f"⚠️  Худшая: {worst['ticker']} ({worst['avg_change_percent']:+.2f}%)" + " " * 5 + Fore.CYAN + "║")
            
            print(Fore.CYAN + "║ " + Fore.GREEN + f"💰 Цена: {best['last_price']:.2f}" + 
                  " " * 25 + Fore.RED + f"💰 Цена: {worst['last_price']:.2f}" + " " * 15 + Fore.CYAN + "║")
        
        # Прогнозы на ближайшие дни
        print(Fore.CYAN + "╠" + "─" * 78 + "╣")
        print(Fore.CYAN + "║" + Fore.WHITE + " " * 28 + "📅 ПРОГНОЗЫ НА БЛИЖАЙШИЕ ДНИ" + " " * 26 + Fore.CYAN + "║")
        print(Fore.CYAN + "╠" + "─" * 78 + "╣")
        
        # Показываем прогнозы для лучшего тикера
        if self.results and 'day_7' in self.results[0]['predictions']:
            best_ticker = self.results[0]
            
            for day in [1, 7, 14, 30]:
                pred_key = f'day_{day}'
                if pred_key in best_ticker['predictions']:
                    pred = best_ticker['predictions'][pred_key]
                    pred_date = (datetime.now() + timedelta(days=day)).strftime('%d.%m')
                    
                    # Цвет для прогноза
                    if pred.get('change_percent', 0) > 0:
                        pred_color = Fore.GREEN
                        pred_symbol = "📈"
                    elif pred.get('change_percent', 0) < 0:
                        pred_color = Fore.RED
                        pred_symbol = "📉"
                    else:
                        pred_color = Fore.YELLOW
                        pred_symbol = "➡️"
                    
                    print(Fore.CYAN + "║ " + Fore.WHITE + f"📅 Через {day:2d} дн. ({pred_date}): " + 
                          pred_color + f"{pred_symbol} {pred.get('change_percent', 0):+.2f}%" + 
                          Fore.WHITE + f" | Цена: {pred_color}{pred.get('price', 0):.2f}" + 
                          Fore.WHITE + f" | Уверенность: {Fore.CYAN}{pred.get('confidence', 0)*100:.1f}%" + " " * 5 + Fore.CYAN + "║")
        
        # Нижняя граница
        print(Fore.CYAN + "╚" + "═" * 78 + "╝")
        
        # Информация о сохраненных файлах
        print(Fore.CYAN + "\n💾 Отчеты сохранены:")
        print(Fore.CYAN + "─" * 50)
        
        # Генерируем отчеты и показываем пути
        excel_path = self.generate_excel_report()
        
        if excel_path:
            print(Fore.WHITE + f"📄 Excel: {Fore.CYAN}{excel_path}")
        
        print(Fore.CYAN + "─" * 50)
        
        # Заключительное сообщение
        print(Fore.GREEN + "\n🎉 Анализ успешно завершен! Используйте отчеты для принятия инвестиционных решений.")
        print(Fore.YELLOW + "⚠️  Помните: все прогнозы являются вероятностными оценками.")

