import threading
import time
import random

# Variables compartidas (Memoriacomún entre hilos)
# Todos los hilos pueden leer y escribir aquí.
ultima_data_procesada = "Ninguna"
funcionando = True

# --- TAREA PESADA (Simula tu IA/Inferencia) ---
def tarea_pesada_ia():
    global ultima_data_procesada
    
    while funcionando:
        print("   [IA] Iniciando cálculo complejo...")
        
        # Simulamos que la IA tarda 3 segundos en pensar
        time.sleep(3) 
        
        # Generamos un resultado
        resultado = random.choice(["Gato", "Perro", "Persona", "Coche"])
        ultima_data_procesada = resultado
        print(f"   [IA] ¡Terminé! Detecté: {resultado}")

# --- TAREA RÁPIDA (Simula tu Cámara/UI) ---
def bucle_principal():
    print("[MAIN] Iniciando sistema de radar...")
    
    # 1. Crear el hilo
    # target=Función que correrá el hilo
    # daemon=True significa que si el programa principal cierra, este hilo muere también.
    hilo_ia = threading.Thread(target=tarea_pesada_ia, daemon=True)
    
    # 2. Iniciar el hilo (Aquí se 'bifurca' la ejecución)
    hilo_ia.start()
    
    # 3. Bucle principal (Muestra datos mientras la IA trabaja al fondo)
    try:
        contador = 0
        while True:
            # Esto simula ver un frame de cámara (muy rápido, 10 FPS)
            time.sleep(0.1) 
            
            # Imprimimos qué está viendo el usuario AHORA
            # Nota cómo 'ultima_data_procesada' cambia sola cuando la IA termina
            print(f"\r[CAMARA] Frame {contador} | Última detección: {ultima_data_procesada}", end="")
            contador += 1
            
    except KeyboardInterrupt:
        print("\n[MAIN] Apagando...")
        global funcionando
        funcionando = False
        hilo_ia.join() # Esperar a que el hilo termine ordenadamente

if __name__ == "__main__":
    bucle_principal()