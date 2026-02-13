"""
State Manager - Máquina de Estados Finitos
Implementación basada en el diagrama de estados Mermaid proporcionado
States: Booting, Running, Throttling, Error
"""

import logging
import time
from enum import Enum
from typing import Callable, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class SystemState(Enum):
    """Estados del sistema según diagrama de estados"""
    BOOTING = "Booting"
    RUNNING = "Running"
    THROTTLING = "Throttling"
    ERROR = "Error"
    SHUTDOWN = "Shutdown"


class StateManager:
    """Gestor de máquina de estados del sistema"""
    
    def __init__(self):
        self.current_state = SystemState.BOOTING
        self.previous_state: Optional[SystemState] = None
        self._lock = Lock()
        
        # Callbacks para entry/exit actions
        self._entry_callbacks = {}
        self._exit_callbacks = {}
        
        # Registro de transiciones
        self.transition_history = []
        
    def register_entry_callback(self, state: SystemState, callback: Callable):
        """
        Registra callback que se ejecuta al ENTRAR a un estado
        
        Args:
            state: Estado objetivo
            callback: Función a ejecutar (sin argumentos)
        """
        self._entry_callbacks[state] = callback
        
    def register_exit_callback(self, state: SystemState, callback: Callable):
        """
        Registra callback que se ejecuta al SALIR de un estado
        
        Args:
            state: Estado origen
            callback: Función a ejecutar (sin argumentos)
        """
        self._exit_callbacks[state] = callback
    
    def transition_to(self, new_state: SystemState, reason: str = "") -> bool:
        """
        Transiciona a un nuevo estado
        
        Args:
            new_state: Estado destino
            reason: Razón de la transición (para logging)
        
        Returns:
            True si la transición fue exitosa
        """
        with self._lock:
            if new_state == self.current_state:
                logger.debug(f"Ya estamos en estado {new_state.value}")
                return True
            
            old_state = self.current_state
            
            # Validar transición según diagrama de estados
            if not self._is_valid_transition(old_state, new_state):
                logger.warning(
                    f"Transición inválida: {old_state.value} -> {new_state.value}"
                )
                return False
            
            logger.info(
                f"Transición: {old_state.value} -> {new_state.value} | Razón: {reason}"
            )
            
            # Ejecutar exit callback del estado anterior
            if old_state in self._exit_callbacks:
                try:
                    self._exit_callbacks[old_state]()
                except Exception as e:
                    logger.error(f"Error en exit callback de {old_state.value}: {e}")
            
            # Cambiar estado
            self.previous_state = old_state
            self.current_state = new_state
            
            # Registrar transición
            self.transition_history.append({
                'from': old_state,
                'to': new_state,
                'reason': reason,
                'timestamp': time.time()
            })
            
            # Ejecutar entry callback del nuevo estado
            if new_state in self._entry_callbacks:
                try:
                    self._entry_callbacks[new_state]()
                except Exception as e:
                    logger.error(f"Error en entry callback de {new_state.value}: {e}")
            
            return True
    
    def _is_valid_transition(self, from_state: SystemState, to_state: SystemState) -> bool:
        """
        Valida si una transición es permitida según diagrama de estados
        
        Transiciones válidas:
        - Booting -> Running (Init_Success)
        - Booting -> Error (Init_Fail)
        - Running -> Throttling (Overheat)
        - Running -> Error (Exception)
        - Running -> Shutdown (Power_Off)
        - Throttling -> Running (Cooled)
        - Throttling -> Error (Critical)
        - Error -> Booting (Watchdog)
        """
        valid_transitions = {
            SystemState.BOOTING: [SystemState.RUNNING, SystemState.ERROR],
            SystemState.RUNNING: [SystemState.THROTTLING, SystemState.ERROR, SystemState.SHUTDOWN],
            SystemState.THROTTLING: [SystemState.RUNNING, SystemState.ERROR],
            SystemState.ERROR: [SystemState.BOOTING],
            SystemState.SHUTDOWN: [],  # Estado terminal
        }
        
        return to_state in valid_transitions.get(from_state, [])
    
    def get_state(self) -> SystemState:
        """Retorna el estado actual"""
        with self._lock:
            return self.current_state
    
    def is_in_state(self, state: SystemState) -> bool:
        """Verifica si estamos en un estado específico"""
        return self.current_state == state
    
    def get_state_info(self) -> dict:
        """Retorna información completa del estado actual"""
        with self._lock:
            return {
                'current': self.current_state.value,
                'previous': self.previous_state.value if self.previous_state else None,
                'transition_count': len(self.transition_history),
            }
