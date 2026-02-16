import time
import traceback


# NO importes aquí arriba para probar
# from src.core.context import Context
# from src.core.init import InitState

if __name__ == "__main__":
    print("[Main] Iniciando python...", flush=True)
    
    try:
        print("[Main] Importando dependencias...", flush=True)
        from src.core.context import Context
        from src.core.init import InitState
        print("[Main] Importaciones listas. Iniciando App...", flush=True)

        context = Context(InitState())
        while True:
            context.run()
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n[MAIN] Apagando...", flush=True)
    except Exception as e:
        print(f"\n[CRASH] Error: {e}", flush=True)
        traceback.print_exc()