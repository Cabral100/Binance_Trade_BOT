import time
import numpy as np
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance.enums import *
import ta
from datetime import datetime
import os
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("solana_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY', 'insert your API_KEY ')
API_SECRET = os.getenv('BINANCE_API_SECRET', 'insert your API_SECRET')

SYMBOL = 'SOLUSDT'  
INTERVAL = Client.KLINE_INTERVAL_5MINUTE 
LIMIT = 100  
CHECK_INTERVAL = 300  # Verificar a cada 5 minutos (300 segundos)

# Parâmetros de trading
MIN_QUANTIDADE = 0.1  # Quantidade mínima para negociar (ajuste conforme necessário)
USAR_PERCENTUAL_SALDO = True  # Se True, usa porcentagem do saldo disponível
PERCENTUAL_SALDO = 10  # Percentual do saldo USDT a usar em cada operação (10%)
STOP_LOSS_PERCENT = 2.5  # Stop Loss em porcentagem
TAKE_PROFIT_PERCENT = 5.0  # Take Profit em porcentagem

# Inicializa o cliente da Binance
try:
    client = Client(API_KEY, API_SECRET)
    logger.info("Cliente Binance inicializado com sucesso")
except Exception as e:
    logger.error(f"Erro ao inicializar cliente Binance: {e}")
    exit(1)

def formatar_numero(valor, precisao=8):
    """Formata um número com a precisão específica removendo zeros à direita."""
    formato = f"{{:.{precisao}f}}"
    resultado = formato.format(valor).rstrip('0').rstrip('.')
    return resultado if resultado else '0'

def obter_informacoes_simbolo():
    """Obtém informações de trading para o símbolo."""
    try:
        info = client.get_symbol_info(SYMBOL)
        exchange_info = client.get_exchange_info()
        
        symbol_info = None
        for s in exchange_info['symbols']:
            if s['symbol'] == SYMBOL:
                symbol_info = s
                break
        
        if symbol_info:
            # Encontrar a precisão de quantidade e preço
            lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            price_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
            
            quantidade_precision = 0
            preco_precision = 0
            
            if lot_size_filter:
                step_size = float(lot_size_filter['stepSize'])
                quantidade_precision = len(str(step_size).rstrip('0').split('.')[-1]) if '.' in str(step_size) else 0
            
            if price_filter:
                tick_size = float(price_filter['tickSize'])
                preco_precision = len(str(tick_size).rstrip('0').split('.')[-1]) if '.' in str(tick_size) else 0
            
            logger.info(f"Precisão de quantidade: {quantidade_precision}, Precisão de preço: {preco_precision}")
            return {
                'quantidade_precision': quantidade_precision,
                'preco_precision': preco_precision,
                'min_qty': float(lot_size_filter['minQty']) if lot_size_filter else 0.001,
                'min_notional': float(next((f for f in symbol_info['filters'] if f['filterType'] == 'MIN_NOTIONAL'), {'minNotional': '10'})['minNotional'])
            }
        else:
            logger.error(f"Não foi possível encontrar informações para o símbolo {SYMBOL}")
            return {
                'quantidade_precision': 3,  # Valor padrão
                'preco_precision': 2,      # Valor padrão
                'min_qty': 0.001,          # Valor padrão
                'min_notional': 10         # Valor padrão
            }
    except Exception as e:
        logger.error(f"Erro ao obter informações do símbolo: {e}")
        return {
            'quantidade_precision': 3,  # Valor padrão
            'preco_precision': 2,      # Valor padrão
            'min_qty': 0.001,          # Valor padrão
            'min_notional': 10         # Valor padrão
        }

def obter_saldo(asset):
    """Obtém o saldo disponível de um ativo específico."""
    try:
        account = client.get_account()
        for balance in account['balances']:
            if balance['asset'] == asset:
                return float(balance['free'])
        return 0.0
    except Exception as e:
        logger.error(f"Erro ao obter saldo de {asset}: {e}")
        return 0.0

def calcular_quantidade_compra(preco_atual, symbol_info):
    """Calcula a quantidade a ser comprada com base no saldo USDT e regras do par."""
    try:
        saldo_usdt = obter_saldo('USDT')
        logger.info(f"Saldo USDT disponível: {saldo_usdt}")
        
        if USAR_PERCENTUAL_SALDO:
            # Usar percentual do saldo USDT
            valor_compra = saldo_usdt * (PERCENTUAL_SALDO / 100)
        else:
            # Usar quantidade fixa
            valor_compra = MIN_QUANTIDADE * preco_atual
        
        # Verificar valor mínimo
        if valor_compra < symbol_info['min_notional']:
            logger.warning(f"Valor de compra {valor_compra} abaixo do mínimo necessário {symbol_info['min_notional']}")
            valor_compra = symbol_info['min_notional']
        
        # Calcular quantidade
        quantidade = valor_compra / preco_atual
        
        # Garantir quantidade mínima
        if quantidade < symbol_info['min_qty']:
            logger.warning(f"Quantidade calculada {quantidade} abaixo do mínimo permitido {symbol_info['min_qty']}")
            quantidade = symbol_info['min_qty']
        
        # Arredondar para a precisão correta
        quantidade = round(quantidade, symbol_info['quantidade_precision'])
        
        logger.info(f"Quantidade calculada para compra: {quantidade} SOL")
        return quantidade
    except Exception as e:
        logger.error(f"Erro ao calcular quantidade de compra: {e}")
        return MIN_QUANTIDADE  # Retorna quantidade mínima em caso de erro

def obter_dados_historicos():
    """Obtém dados históricos do par selecionado."""
    try:
        logger.info(f"Obtendo dados históricos para {SYMBOL} no intervalo {INTERVAL}...")
        candles = client.get_klines(symbol=SYMBOL, interval=INTERVAL, limit=LIMIT)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                         'close_time', 'quote_asset_volume', 'number_of_trades',
                                         'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        
        # Converter colunas para valores numéricos
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        # Converter timestamp para datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        logger.info(f"Dados obtidos com sucesso: {len(df)} candles")
        return df
    except Exception as e:
        logger.error(f"Erro ao obter dados históricos: {e}")
        return None

def calcular_indicadores(df):
    """Calcula indicadores técnicos no DataFrame."""
    try:
        # RSI (Índice de Força Relativa)
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        
        # MACD (Moving Average Convergence Divergence)
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # Médias Móveis
        df['sma_9'] = ta.trend.SMAIndicator(df['close'], window=9).sma_indicator()
        df['sma_20'] = ta.trend.SMAIndicator(df['close'], window=20).sma_indicator()
        df['sma_50'] = ta.trend.SMAIndicator(df['close'], window=50).sma_indicator()
        df['ema_9'] = ta.trend.EMAIndicator(df['close'], window=9).ema_indicator()
        
        # Bollinger Bands
        bollinger = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['bb_high'] = bollinger.bollinger_hband()
        df['bb_low'] = bollinger.bollinger_lband()
        df['bb_mid'] = bollinger.bollinger_mavg()
        df['bb_pct'] = bollinger.bollinger_pband()
        
        # Stochastic Oscillator
        stoch = ta.momentum.StochasticOscillator(df['high'], df['low'], df['close'], window=14, smooth_window=3)
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()
        
        logger.info("Indicadores calculados com sucesso")
        return df
    except Exception as e:
        logger.error(f"Erro ao calcular indicadores: {e}")
        return df

def analisar_mercado(df):
    """Analisa o mercado e retorna uma decisão de trading."""
    try:
        if df is None or len(df) < 50:
            logger.warning("Dados insuficientes para análise")
            return "AGUARDAR", {}
            
        # Últimos dois candles para comparação
        penultima_linha = df.iloc[-2]
        ultima_linha = df.iloc[-1]
        
        # Coletar métricas para logging
        metricas = {
            'preco': ultima_linha['close'],
            'rsi': ultima_linha['rsi'],
            'sma_9': ultima_linha['sma_9'],
            'sma_20': ultima_linha['sma_20'],
            'macd': ultima_linha['macd'],
            'macd_signal': ultima_linha['macd_signal'],
            'stoch_k': ultima_linha['stoch_k'],
            'stoch_d': ultima_linha['stoch_d'],
            'bb_pct': ultima_linha['bb_pct']
        }
        
        # 1. Verificar RSI (sobrecomprado/sobrevendido)
        rsi = ultima_linha['rsi']
        rsi_anterior = penultima_linha['rsi']
        sobrevendido = rsi < 30
        sobrecomprado = rsi > 70
        rsi_subindo = rsi > rsi_anterior
        
        # 2. Verificar cruzamento de MACD
        macd = ultima_linha['macd']
        macd_signal = ultima_linha['macd_signal']
        macd_anterior = penultima_linha['macd']
        macd_signal_anterior = penultima_linha['macd_signal']
        
        # Verificar cruzamento para cima do MACD
        cruzamento_macd_cima = (macd > macd_signal) and (macd_anterior <= macd_signal_anterior)
        # Verificar cruzamento para baixo do MACD
        cruzamento_macd_baixo = (macd < macd_signal) and (macd_anterior >= macd_signal_anterior)
        
        # 3. Verificar médias móveis
        preco_atual = ultima_linha['close']
        sma_9 = ultima_linha['sma_9']
        sma_20 = ultima_linha['sma_20']
        sma_50 = ultima_linha['sma_50'] if 'sma_50' in ultima_linha else 0
        
        acima_sma9 = preco_atual > sma_9
        acima_sma20 = preco_atual > sma_20
        tendencia_alta = sma_9 > sma_20 and sma_20 > sma_50 if sma_50 > 0 else sma_9 > sma_20
        tendencia_baixa = sma_9 < sma_20 and sma_20 < sma_50 if sma_50 > 0 else sma_9 < sma_20
        
        # 4. Verificar Bollinger Bands
        bb_high = ultima_linha['bb_high']
        bb_low = ultima_linha['bb_low']
        bb_mid = ultima_linha['bb_mid']
        bb_pct = ultima_linha['bb_pct']
        proxim_banda_inferior = bb_pct < 0.2
        proxim_banda_superior = bb_pct > 0.8
        
        # 5. Verificar Stochastic
        stoch_k = ultima_linha['stoch_k']
        stoch_d = ultima_linha['stoch_d']
        stoch_k_anterior = penultima_linha['stoch_k']
        stoch_d_anterior = penultima_linha['stoch_d']
        
        stoch_sobrevendido = stoch_k < 20 and stoch_d < 20
        stoch_sobrecomprado = stoch_k > 80 and stoch_d > 80
        cruzamento_stoch_cima = (stoch_k > stoch_d) and (stoch_k_anterior <= stoch_d_anterior)
        cruzamento_stoch_baixo = (stoch_k < stoch_d) and (stoch_k_anterior >= stoch_d_anterior)
        
        # Lógica de decisão combinando indicadores
        sinais_compra = 0
        sinais_venda = 0
        
        # Sinais de compra
        if sobrevendido: sinais_compra += 1
        if cruzamento_macd_cima: sinais_compra += 1
        if proxim_banda_inferior: sinais_compra += 1
        if stoch_sobrevendido: sinais_compra += 1
        if cruzamento_stoch_cima and stoch_k < 50: sinais_compra += 1
        if tendencia_alta: sinais_compra += 1
        
        # Sinais de venda
        if sobrecomprado: sinais_venda += 1
        if cruzamento_macd_baixo: sinais_venda += 1
        if proxim_banda_superior: sinais_venda += 1
        if stoch_sobrecomprado: sinais_venda += 1
        if cruzamento_stoch_baixo and stoch_k > 50: sinais_venda += 1
        if tendencia_baixa: sinais_venda += 1
        
        # Decisão final (precisamos de pelo menos 3 sinais concordantes)
        if sinais_compra >= 3 and sinais_compra > sinais_venda:
            logger.info(f"Decisão: COMPRAR - {sinais_compra} sinais de compra vs {sinais_venda} de venda")
            return "COMPRAR", metricas
        elif sinais_venda >= 3 and sinais_venda > sinais_compra:
            logger.info(f"Decisão: VENDER - {sinais_venda} sinais de venda vs {sinais_compra} de compra")
            return "VENDER", metricas
        else:
            logger.info(f"Decisão: AGUARDAR - {sinais_compra} sinais de compra vs {sinais_venda} de venda")
            return "AGUARDAR", metricas
            
    except Exception as e:
        logger.error(f"Erro ao analisar mercado: {e}")
        return "AGUARDAR", {'erro': str(e)}

def executar_ordem_compra(quantidade, symbol_info):
    """Executa uma ordem de compra."""
    try:
        # Verificar saldo antes de comprar
        saldo_usdt = obter_saldo('USDT')
        
        if saldo_usdt < quantidade * float(client.get_ticker(symbol=SYMBOL)['lastPrice']):
            logger.warning(f"Saldo USDT insuficiente: {saldo_usdt}")
            return False
            
        # Formatar quantidade com precisão correta
        quantidade_formatada = formatar_numero(quantidade, symbol_info['quantidade_precision'])
        
        logger.info(f"Executando ordem de COMPRA para {SYMBOL}, quantidade: {quantidade_formatada}")
        
        ordem = client.create_order(
            symbol=SYMBOL,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantidade_formatada
        )
        
        logger.info(f"Ordem de COMPRA executada: {ordem['orderId']}")
        # Registrar dados completos em um arquivo separado para análise
        with open("ordens_executadas.log", "a") as f:
            f.write(f"{datetime.now()} - COMPRA - {ordem}\n")
            
        return True
        
    except BinanceAPIException as e:
        logger.error(f"Erro da API Binance ao executar compra: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao executar ordem de compra: {e}")
        return False

def executar_ordem_venda(symbol_info):
    """Executa uma ordem de venda."""
    try:
        # Obter saldo de SOL
        saldo_sol = obter_saldo('SOL')
        
        if saldo_sol <= 0:
            logger.warning(f"Sem saldo de SOL para vender: {saldo_sol}")
            return False
            
        # Garantir que respeita a quantidade mínima
        if saldo_sol < symbol_info['min_qty']:
            logger.warning(f"Saldo SOL abaixo do mínimo permitido: {saldo_sol} < {symbol_info['min_qty']}")
            return False
            
        # Formatar quantidade com precisão correta
        quantidade_formatada = formatar_numero(saldo_sol, symbol_info['quantidade_precision'])
        
        logger.info(f"Executando ordem de VENDA para {SYMBOL}, quantidade: {quantidade_formatada}")
        
        ordem = client.create_order(
            symbol=SYMBOL,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=quantidade_formatada
        )
        
        logger.info(f"Ordem de VENDA executada: {ordem['orderId']}")
        # Registrar dados completos em um arquivo separado para análise
        with open("ordens_executadas.log", "a") as f:
            f.write(f"{datetime.now()} - VENDA - {ordem}\n")
            
        return True
        
    except BinanceAPIException as e:
        logger.error(f"Erro da API Binance ao executar venda: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao executar ordem de venda: {e}")
        return False

def verificar_saldo():
    """Verifica o saldo disponível na conta."""
    try:
        account = client.get_account()
        balances = account['balances']
        
        moedas_interesse = ['SOL', 'USDT']
        saldos = {}
        
        for balance in balances:
            if balance['asset'] in moedas_interesse:
                saldo_livre = float(balance['free'])
                saldo_bloqueado = float(balance['locked'])
                logger.info(f"Saldo {balance['asset']}: {saldo_livre} (livre) + {saldo_bloqueado} (bloqueado)")
                saldos[balance['asset']] = saldo_livre
                
        return saldos
    except Exception as e:
        logger.error(f"Erro ao verificar saldo: {e}")
        return {}

def main():
    """Função principal do bot de trading."""
    logger.info(f"=" * 60)
    logger.info(f"BOT DE TRADING AUTOMÁTICO PARA SOLANA/USDT")
    logger.info(f"=" * 60)
    logger.info(f"Configuração:")
    logger.info(f"- Par: {SYMBOL}")
    logger.info(f"- Intervalo: {INTERVAL}")
    logger.info(f"- Verificação a cada: {CHECK_INTERVAL} segundos")
    
    # Verificar conexão com Binance
    try:
        status = client.get_system_status()
        logger.info(f"Status do sistema Binance: {status['msg']}")
    except Exception as e:
        logger.error(f"Erro ao conectar com a Binance: {e}")
        logger.error("Verifique suas chaves API e sua conexão com a internet.")
        return
    
    # Obter informações do símbolo para formatação correta
    symbol_info = obter_informacoes_simbolo()
    
    # Verificar saldo inicial
    saldos = verificar_saldo()
    logger.info(f"Saldo inicial: {saldos}")
    
    # Variáveis para controle de posição
    em_posicao = saldos.get('SOL', 0) > symbol_info['min_qty']
    preco_entrada = None
    
    if em_posicao:
        logger.info(f"Iniciando com posição aberta em SOL: {saldos.get('SOL', 0)}")
    else:
        logger.info("Iniciando sem posição aberta")
    
    # Loop principal
    while True:
        try:
            logger.info(f"\n{'='*50}")
            logger.info(f"Execução em: {datetime.now()}")
            
            # 1. Obter dados históricos
            df = obter_dados_historicos()
            
            if df is not None and not df.empty:
                # 2. Calcular indicadores
                df = calcular_indicadores(df)
                
                # 3. Obter preço atual
                preco_atual = df['close'].iloc[-1]
                logger.info(f"Preço atual de {SYMBOL}: {preco_atual}")
                
                # 4. Verificar saldo atual
                saldos = verificar_saldo()
                em_posicao = saldos.get('SOL', 0) > symbol_info['min_qty']
                
                # 5. Analisar mercado e tomar decisão
                decisao, metricas = analisar_mercado(df)
                
                # Logar métricas principais
                logger.info(f"RSI: {metricas.get('rsi', 0):.2f}, MACD: {metricas.get('macd', 0):.2f}, Signal: {metricas.get('macd_signal', 0):.2f}")
                logger.info(f"Stoch K: {metricas.get('stoch_k', 0):.2f}, D: {metricas.get('stoch_d', 0):.2f}, BB%: {metricas.get('bb_pct', 0):.2f}")
                
                # 6. Executar ordem com base na decisão e posição atual
                if decisao == "COMPRAR" and not em_posicao:
                    # Calcular quantidade para compra
                    quantidade = calcular_quantidade_compra(preco_atual, symbol_info)
                    
                    if quantidade > 0:
                        # Executar compra
                        if executar_ordem_compra(quantidade, symbol_info):
                            logger.info(f"COMPRA EXECUTADA: {quantidade} SOL a ~{preco_atual} USDT")
                            em_posicao = True
                            preco_entrada = preco_atual
                            saldos = verificar_saldo()  # Atualizar saldos
                            
                elif decisao == "VENDER" and em_posicao:
                    # Executar venda
                    if executar_ordem_venda(symbol_info):
                        logger.info(f"VENDA EXECUTADA: {saldos.get('SOL', 0)} SOL a ~{preco_atual} USDT")
                        em_posicao = False
                        preco_entrada = None
                        saldos = verificar_saldo()  # Atualizar saldos
                
                # 7. Verificar stop loss ou take profit se tiver posição aberta
                elif em_posicao and preco_entrada is not None:
                    variacao_percentual = ((preco_atual - preco_entrada) / preco_entrada) * 100
                    
                    if variacao_percentual <= -STOP_LOSS_PERCENT:
                        logger.info(f"STOP LOSS ACIONADO: Variação de {variacao_percentual:.2f}%")
                        
                        if executar_ordem_venda(symbol_info):
                            logger.info(f"VENDA POR STOP LOSS: {saldos.get('SOL', 0)} SOL a ~{preco_atual} USDT")
                            em_posicao = False
                            preco_entrada = None
                            saldos = verificar_saldo()
                            
                    elif variacao_percentual >= TAKE_PROFIT_PERCENT:
                        logger.info(f"TAKE PROFIT ACIONADO: Variação de {variacao_percentual:.2f}%")
                        
                        if executar_ordem_venda(symbol_info):
                            logger.info(f"VENDA POR TAKE PROFIT: {saldos.get('SOL', 0)} SOL a ~{preco_atual} USDT")
                            em_posicao = False
                            preco_entrada = None
                            saldos = verificar_saldo()
                
            else:
                logger.warning("Não foi possível obter dados históricos. Tentando novamente na próxima iteração.")
                
        except Exception as e:
            logger.error(f"Erro no loop principal: {e}")
        
        # Aguardar até próxima verificação
        logger.info(f"Aguardando {CHECK_INTERVAL/60:.1f} minutos até a próxima análise...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot finalizado pelo usuário.")
    except Exception as e:
        logger.error(f"Erro crítico: {e}")