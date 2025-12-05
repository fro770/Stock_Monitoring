## 🚀 Оптимизированные ансамбли (режим 4)

### Новые возможности:
1. **Автоматическая оптимизация весов** - ML модели взвешиваются на основе их производительности
2. **Расширенные признаки** - +30+ технических и статистических признаков
3. **Композитный score** - учитывает рост, уверенность и согласованность
4. **Кэширование** - ускорение повторных анализов

### Используемые модели:
- Трендовый анализатор
- FinRL LLM модель
- Random Forest
- XGBoost
- LightGBM

### Как использовать:
```bash
# Через скрипт
python analysis/main.py
# Выберите режим 4 в меню

# Или напрямую
python analysis/main_optimized.py --mode 4 --top-n 100 --min-confidence 0.7

D:\STOCK_MONITORING
│   init_db_and_load.py
│   make_excel.py
│   moex_all_shares.csv
│   moex_all_shares.xlsx
│   README.md
│   requirements.txt
│
├───analysis
│   │   analyzer.py
│   │   main.py
│   │   reporter.py
│   │   __init__.py
│   │
│   ├───core
│   │   │   config.py
│   │   │   data_loader.py
│   │   │   moex_client.py
│   │   │   validator.py
│   │   │   __init__.py
│   │   │
│   │   └───__pycache__
│   │
│   ├───models
│   │   │   base_predictor.py
│   │   │   ensemble.py
│   │   │   finrl_predictor.py
│   │   │   model_manager.py
│   │   │   trend_predictor.py
│   │   │   __init__.py
│   │   │
│   │   └───__pycache__
│   │
│   ├───utils
│   │       helpers.py
│   │       logger.py
│   │       __init__.py
│   │
│   └───__pycache__
│
├───data
│   │   stocks.db
│   │
│   └───__pycache__
│
├───logs
│       analysis.log
│       analysis_main.log
│       db_init.log
│       download_data.log
│       make_excel.log
│       stock_data_fetcher.log
│
├───models
│   │   llm_loader.py
│   │   __init__.py
│   │
│   ├───finbert-tone
│   │       .gitattributes
│   │       config.json
│   │       pytorch_model.bin
│   │       README.md
│   │       tf_model.h5
│   │       vocab.txt
│   │
│   ├───finrl_output
│   │       .gitattributes
│   │       adapter_config.json
│   │       adapter_model.safetensors
│   │       added_tokens.json
│   │       chat_template.jinja
│   │       merges.txt
│   │       optimizer.pt
│   │       README.md
│   │       rng_state.pth
│   │       scheduler.pt
│   │       special_tokens_map.json
│   │       tokenizer.json
│   │       tokenizer_config.json
│   │       trainer_state.json
│   │       training_args.bin
│   │       vocab.json
│   │
│   ├───ml_models
│   │   │   finrl_predictor.py
│   │   │   lstm_model.py
│   │   │
│   │   └───__pycache__
│   │
│   ├───prediction
│   │   │   ensemble.py
│   │   │   predict.py
│   │   │
│   │   └───__pycache__
│   │
│   ├───Qwen3-4B-FinRL-ckpt_1K
│   │       .gitattributes
│   │       adapter_config.json
│   │       adapter_model.safetensors
│   │       added_tokens.json
│   │       chat_template.jinja
│   │       merges.txt
│   │       optimizer.pt
│   │       README.md
│   │       rng_state.pth
│   │       scheduler.pt
│   │       special_tokens_map.json
│   │       tokenizer.json
│   │       tokenizer_config.json
│   │       trainer_state.json
│   │       training_args.bin
│   │       vocab.json
│   │
│   └───sentiment
│       │   analyzer.py
│       │   whisper_analyzer.py
│       │
│       └───__pycache__
│
└───reports