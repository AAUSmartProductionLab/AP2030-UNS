import mqttService from './MqttService';
import { toast } from 'react-toastify';

/**
 * SystemControlService - Overarching state machine controller
 * 
 * This service coordinates state transitions across all subsystems:
 * - Planar Controller
 * - Behavior Tree Controller  
 * - Production Modules (Filling, Loading, etc.)
 * 
 * When a system-wide state change is requested, this service sends
 * the appropriate state command to all registered subsystems.
 * 
 * Implements PackML state machine transitions:
 * - Start: Idle → Starting → Execute
 * - Stop: * → Stopping → Stopped
 * - Reset: Stopped/Complete/Aborted → Resetting → Idle
 * - Hold: Execute → Holding → Held
 * - Unhold: Held → Unholding → Execute
 * - Suspend: Execute → Suspending → Suspended
 * - Unsuspend: Suspended → Unsuspending → Execute
 * - Abort: * → Aborting → Aborted
 * - Clear: Aborted → Clearing → Stopped
 */
class SystemControlService {
  // Define subsystem topics that should receive state commands
  static SUBSYSTEMS = {
    PLANAR: 'NN/Nybrovej/InnoLab/Planar/CMD/State',
    BT_CONTROLLER: 'NN/Nybrovej/InnoLab/bt_controller/CMD/State',
    FILLING: 'NN/Nybrovej/InnoLab/Filling/CMD/State',
    LOADING: 'NN/Nybrovej/InnoLab/Loading/CMD/State',
    STOPPERING: 'NN/Nybrovej/InnoLab/Stoppering/CMD/State',
    UNLOADING: 'NN/Nybrovej/InnoLab/Unloading/CMD/State',
    CAMERA: 'NN/Nybrovej/InnoLab/Camera/CMD/State',
  };

  // Valid PackML commands (what the user sends)
  static COMMANDS = {
    START: 'Start',
    STOP: 'Stop',
    RESET: 'Reset',
    HOLD: 'Hold',
    UNHOLD: 'Unhold',
    SUSPEND: 'Suspend',
    UNSUSPEND: 'Unsuspend',
    ABORT: 'Abort',
    CLEAR: 'Clear',
  };

  // PackML States (actual machine states)
  static STATES = {
    STOPPED: 'Stopped',
    STARTING: 'Starting',
    IDLE: 'Idle',
    EXECUTE: 'Execute',
    COMPLETING: 'Completing',
    COMPLETE: 'Complete',
    RESETTING: 'Resetting',
    HOLDING: 'Holding',
    HELD: 'Held',
    UNHOLDING: 'Unholding',
    SUSPENDING: 'Suspending',
    SUSPENDED: 'Suspended',
    UNSUSPENDING: 'Unsuspending',
    STOPPING: 'Stopping',
    ABORTING: 'Aborting',
    ABORTED: 'Aborted',
    CLEARING: 'Clearing',
  };

  // State transition timing (ms) - how long transitioning states last
  static TRANSITION_DELAY = 200;

  // Track which subsystems are enabled for system-wide control
  enabledSubsystems = new Set([
    'PLANAR',
    'BT_CONTROLLER',
  ]);

  // Current system state (PackML state)
  currentState = SystemControlService.STATES.STOPPED;
  // Timestamp of last state change
  lastStateChangeTime = null;
  // Timer for automatic state transitions
  transitionTimer = null;

  stateChangeHandlers = [];

  /**
   * Register a handler to be notified of system state changes
   * @param {function} handler Callback function
   * @returns {function} Unsubscribe function
   */
  onStateChange(handler) {
    this.stateChangeHandlers.push(handler);
    return () => {
      this.stateChangeHandlers = this.stateChangeHandlers.filter(h => h !== handler);
    };
  }

  /**
   * Notify all handlers of a state change
   * @param {string} state The new state
   * @param {object} results Results from subsystem commands
   */
  notifyStateChange(state, results = null) {
    // Update internal state
    this.currentState = state;
    this.lastStateChangeTime = new Date();
    
    this.stateChangeHandlers.forEach(handler => {
      try {
        handler(state, results);
      } catch (e) {
        console.error('SystemControlService: Error in state change handler:', e);
      }
    });
  }

  /**
   * Transition to a new state and schedule automatic transition if needed
   * @param {string} newState The state to transition to
   * @param {string} nextState Optional next state for automatic transition
   */
  transitionTo(newState, nextState = null) {
    // Clear any pending transition
    if (this.transitionTimer) {
      clearTimeout(this.transitionTimer);
      this.transitionTimer = null;
    }

    console.log(`SystemControlService: Transitioning to ${newState}`);
    this.notifyStateChange(newState);

    // Schedule automatic transition to next state if specified
    if (nextState) {
      this.transitionTimer = setTimeout(() => {
        console.log(`SystemControlService: Auto-transitioning to ${nextState}`);
        this.notifyStateChange(nextState);
        this.transitionTimer = null;
      }, SystemControlService.TRANSITION_DELAY);
    }
  }

  /**
   * Process a command and perform appropriate state transitions
   * @param {string} command The command to process
   * @returns {boolean} Whether the command was valid for current state
   */
  processCommand(command) {
    const { STATES, COMMANDS } = SystemControlService;
    const currentState = this.currentState;

    switch (command) {
      case COMMANDS.START:
        // Start: Idle → Starting → Execute
        if (currentState === STATES.IDLE) {
          this.transitionTo(STATES.STARTING, STATES.EXECUTE);
          return true;
        }
        console.warn(`SystemControlService: Cannot Start from state ${currentState}`);
        return false;

      case COMMANDS.STOP:
        // Stop: Most states → Stopping → Stopped
        if (currentState !== STATES.STOPPED && currentState !== STATES.STOPPING) {
          this.transitionTo(STATES.STOPPING, STATES.STOPPED);
          return true;
        }
        console.warn(`SystemControlService: Cannot Stop from state ${currentState}`);
        return false;

      case COMMANDS.RESET:
        // Reset: Stopped/Complete/Aborted → Resetting → Idle
        if (currentState === STATES.STOPPED || 
            currentState === STATES.COMPLETE || 
            currentState === STATES.ABORTED) {
          this.transitionTo(STATES.RESETTING, STATES.IDLE);
          return true;
        }
        console.warn(`SystemControlService: Cannot Reset from state ${currentState}`);
        return false;

      case COMMANDS.HOLD:
        // Hold: Execute → Holding → Held
        if (currentState === STATES.EXECUTE) {
          this.transitionTo(STATES.HOLDING, STATES.HELD);
          return true;
        }
        console.warn(`SystemControlService: Cannot Hold from state ${currentState}`);
        return false;

      case COMMANDS.UNHOLD:
        // Unhold: Held → Unholding → Execute
        if (currentState === STATES.HELD) {
          this.transitionTo(STATES.UNHOLDING, STATES.EXECUTE);
          return true;
        }
        console.warn(`SystemControlService: Cannot Unhold from state ${currentState}`);
        return false;

      case COMMANDS.SUSPEND:
        // Suspend: Execute → Suspending → Suspended
        if (currentState === STATES.EXECUTE) {
          this.transitionTo(STATES.SUSPENDING, STATES.SUSPENDED);
          return true;
        }
        console.warn(`SystemControlService: Cannot Suspend from state ${currentState}`);
        return false;

      case COMMANDS.UNSUSPEND:
        // Unsuspend: Suspended → Unsuspending → Execute
        if (currentState === STATES.SUSPENDED) {
          this.transitionTo(STATES.UNSUSPENDING, STATES.EXECUTE);
          return true;
        }
        console.warn(`SystemControlService: Cannot Unsuspend from state ${currentState}`);
        return false;

      case COMMANDS.ABORT:
        // Abort: Any state → Aborting → Aborted
        if (currentState !== STATES.ABORTED && currentState !== STATES.ABORTING) {
          this.transitionTo(STATES.ABORTING, STATES.ABORTED);
          return true;
        }
        console.warn(`SystemControlService: Cannot Abort from state ${currentState}`);
        return false;

      case COMMANDS.CLEAR:
        // Clear: Aborted → Clearing → Stopped
        if (currentState === STATES.ABORTED) {
          this.transitionTo(STATES.CLEARING, STATES.STOPPED);
          return true;
        }
        console.warn(`SystemControlService: Cannot Clear from state ${currentState}`);
        return false;

      default:
        console.error(`SystemControlService: Unknown command ${command}`);
        return false;
    }
  }

  /**
   * Get the current system state
   * @returns {string|null}
   */
  getState() {
    return this.currentState;
  }

  /**
   * Get the timestamp of the last state change
   * @returns {Date|null}
   */
  getLastStateChangeTime() {
    return this.lastStateChangeTime;
  }

  /**
   * Enable or disable a subsystem for system-wide control
   * @param {string} subsystemKey Key from SUBSYSTEMS
   * @param {boolean} enabled Whether to enable
   */
  setSubsystemEnabled(subsystemKey, enabled) {
    if (enabled) {
      this.enabledSubsystems.add(subsystemKey);
    } else {
      this.enabledSubsystems.delete(subsystemKey);
    }
    console.log(`SystemControlService: ${subsystemKey} ${enabled ? 'enabled' : 'disabled'}`);
  }

  /**
   * Check if a subsystem is enabled
   * @param {string} subsystemKey Key from SUBSYSTEMS
   * @returns {boolean}
   */
  isSubsystemEnabled(subsystemKey) {
    return this.enabledSubsystems.has(subsystemKey);
  }

  /**
   * Get list of enabled subsystems
   * @returns {string[]}
   */
  getEnabledSubsystems() {
    return Array.from(this.enabledSubsystems);
  }

  /**
   * Send a state command to a specific subsystem
   * @param {string} subsystemKey Key from SUBSYSTEMS  
   * @param {string} stateId State from STATES
   * @returns {Promise<boolean>}
   */
  async sendSubsystemCommand(subsystemKey, stateId) {
    const topic = SystemControlService.SUBSYSTEMS[subsystemKey];
    if (!topic) {
      console.error(`SystemControlService: Unknown subsystem ${subsystemKey}`);
      return false;
    }
    return mqttService.publishStateCommand(topic, stateId);
  }

  /**
   * Send a state command to all enabled subsystems
   * @param {string} command Command from COMMANDS
   * @returns {Promise<object>} Results keyed by subsystem
   */
  async sendSystemCommand(command) {
    // First, validate and process the state transition locally
    const transitionValid = this.processCommand(command);
    if (!transitionValid) {
      toast.error(`Cannot execute ${command} from current state: ${this.currentState}`);
      return { success: false, reason: 'Invalid state transition' };
    }

    console.log(`SystemControlService: Sending ${command} to all enabled subsystems`);
    
    const results = {};
    const promises = [];

    for (const subsystemKey of this.enabledSubsystems) {
      const topic = SystemControlService.SUBSYSTEMS[subsystemKey];
      if (topic) {
        const promise = mqttService.publishStateCommand(topic, command)
          .then(success => {
            results[subsystemKey] = success;
            return success;
          })
          .catch(err => {
            console.error(`SystemControlService: Error sending to ${subsystemKey}:`, err);
            results[subsystemKey] = false;
            return false;
          });
        promises.push(promise);
      }
    }

    await Promise.all(promises);

    // Check results and show appropriate toast
    const successCount = Object.values(results).filter(Boolean).length;
    const totalCount = Object.keys(results).length;

    if (successCount === totalCount) {
      toast.success(`System ${command} command sent to ${totalCount} subsystem(s)`);
    } else if (successCount > 0) {
      toast.warning(`${command} sent to ${successCount}/${totalCount} subsystems`);
    } else {
      toast.error(`Failed to send ${command} command`);
    }

    return results;
  }

  // Convenience methods for common state transitions
  async startSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.START);
  }

  async stopSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.STOP);
  }

  async resetSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.RESET);
  }

  async holdSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.HOLD);
  }

  async unholdSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.UNHOLD);
  }

  async suspendSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.SUSPEND);
  }

  async unsuspendSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.UNSUSPEND);
  }

  async abortSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.ABORT);
  }

  async clearSystem() {
    return this.sendSystemCommand(SystemControlService.COMMANDS.CLEAR);
  }
}

// Export singleton instance
const systemControlService = new SystemControlService();
export default systemControlService;
export { SystemControlService };
