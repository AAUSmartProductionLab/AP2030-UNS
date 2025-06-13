import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import mqttService from '../services/MqttService';
import { SOPModal } from '../components/SOPModal/SOPModal';
import { sopDefinitions, sopHelpers } from '../data/sopDefinitions';
import '../styles/SOPDashboard.css';

export default function SOPDashboard() {
  const [mqttConnected, setMqttConnected] = useState(false);
  const [activeTasks, setActiveTasks] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [showSOPModal, setShowSOPModal] = useState(false);

  useEffect(() => {
    // Connect to MQTT and subscribe to task topics
    mqttService.ensureConnection();
    
    const unsubscribeConnection = mqttService.onConnectionChange(setMqttConnected);
    
    // Subscribe to intervention task topic only
    const unsubscribeTask = mqttService.onMessage('NN/Nybrovej/InnoLab/Intervention/CMD/Task', handleTaskReceived);

    return () => {
      unsubscribeConnection();
      unsubscribeTask();
    };
  }, [activeSession]);

  const sendTaskResponse = (Uuid, state, notes = '') => {
    const response = {
      Uuid: Uuid,
      State: state,
      OperatorId: 'current-operator',
      Notes: notes
    };
    mqttService.publishTaskRepsonse(response);
  };

  const handleTaskReceived = useCallback((message) => {
    console.log('New task received:', message);
    console.log('Current activeSession:', activeSession);
    
    const task = {
      Uuid: message.Uuid,
      SopId: message.SopId,
      TimeStamp: new Date().toISOString(),
      Status: 'pending',
      Acknowledged: false
    };

    // Get SOP definition
    const sopDefinition = sopDefinitions[message.SopId];
    if (!sopDefinition) {
      console.error(`Unknown SOP ID: ${message.SopId}`);
      sendTaskResponse(message.Uuid, 'FAILURE', `Unknown SOP ID: ${message.SopId}`);
      return;
    }

    const newTask = {
      ...task,
      sopDefinition: sopDefinition
    };

    // Handle different task types based on sopId and session state
    if (sopHelpers.isSessionStarter(message.SopId)) {
      // Session starter (10, 20, 30, etc.) - always add to task list
      newTask.isSessionStarter = true;
      newTask.sessionType = sopDefinition.sessionType;
      setActiveTasks(prev => [...prev, newTask]);
      toast.info(`New session task: ${sopDefinition.title}`);
    } else if (sopHelpers.isSessionCompleter(message.SopId)) {
      // sopId 0 - session completion signal
      if (activeSession) {
        console.log('Session completion signal received');
        setActiveSession(prev => ({
          ...prev,
          canComplete: true,
          completionMessage: newTask
        }));
        toast.success('Session ready for completion!');
      } else {
        console.warn('Received session completion signal but no active session');
        //sendTaskResponse(message.Uuid, 'FAILURE', 'No active session to complete');
      }
    } else if (activeSession && sopHelpers.isSubtaskOf(message.SopId, activeSession.sessionStarterId)) {
      // During active session - add as instruction if it's a subtask of current session
      console.log('Adding subtask to active session');
      setActiveSession(prev => {
        const updatedSession = {
          ...prev,
          instructions: [...prev.instructions, newTask],
          currentInstructionIndex: prev.currentInstructionIndex === -1 ? 0 : prev.currentInstructionIndex
        };
        console.log('Updated session:', updatedSession);
        return updatedSession;
      });
      toast.info(`New instruction: ${sopDefinition.title}`);
    } else if (activeSession && !sopHelpers.isSubtaskOf(message.SopId, activeSession.sessionStarterId)) {
      // Task received during session but not a subtask
      if (sopHelpers.isSessionStarter(message.SopId)) {
        // If it's a session starter, add it to tasks (will be queued)
        newTask.isSessionStarter = true;
        newTask.sessionType = sopDefinition.sessionType;
        setActiveTasks(prev => [...prev, newTask]);
        toast.warn(`Session task queued (another session active): ${sopDefinition.title}`);
      } else {
        // Regular task during session - reject it
        console.warn(`Rejecting task ${message.SopId} - not part of active session`);
        sendTaskResponse(message.Uuid, 'FAILURE', `Task not part of active ${activeSession.sessionType} session`);
        toast.warn(`Task rejected: ${sopDefinition.title} (not part of active session)`);
      }
    } else {
      // No active session - only allow session starters or system tasks
      if (sopHelpers.isSessionStarter(message.SopId) || task.sopDefinition.isSystemStep) {
        setActiveTasks(prev => [...prev, newTask]);
        toast.info(`New task: ${sopDefinition.title}`);
      } else {
        // Regular task without active session - reject it
        console.warn(`Rejecting task ${message.SopId} - no active session for subtask`);
        sendTaskResponse(message.Uuid, 'FAILURE', 'No active session - only session starters allowed');
        toast.warn(`Task rejected: ${sopDefinition.title} (no active session)`);
      }
    }
  }, [activeSession]);

  const acknowledgeTask = (taskUuid) => {
    const task = activeTasks.find(t => t.Uuid === taskUuid);
    if (!task) return;

    // Don't send response here - just mark as acknowledged
    setActiveTasks(prev => 
      prev.map(t => 
        t.Uuid === taskUuid 
          ? { ...t, Acknowledged: true, acknowledgedAt: new Date().toISOString() }
          : t
      )
    );

    toast.success(`Task "${task.sopDefinition.title}" acknowledged`);
  };

  const startSession = (taskUuid) => {
    const task = activeTasks.find(t => t.Uuid === taskUuid);
    if (!task || !task.Acknowledged) return;

    // Send task response when starting session
    sendTaskResponse(taskUuid, 'SUCCESSFUL', 'Session started by operator');

    // Remove task from active tasks
    setActiveTasks(prev => prev.filter(t => t.Uuid !== taskUuid));

    // Initialize new session
    const newSession = {
      sessionId: taskUuid,
      sessionStarterId: task.SopId,
      sessionType: task.sessionType,
      startTime: new Date().toISOString(),
      instructions: [],
      currentInstructionIndex: -1,
      completedInstructions: [],
      canComplete: false,
      completionMessage: null
    };
    
    console.log('Starting new session:', newSession);
    setActiveSession(newSession);
    setShowSOPModal(true);
    
    toast.success(`${task.sopDefinition.title} started - waiting for instructions`);
  };

  const executeTask = (taskUuid) => {
    const task = activeTasks.find(t => t.Uuid === taskUuid);
    if (!task) return;

    // Handle system steps
    if (task.isSystemStep) {
      handleTaskCompletion(taskUuid, true, 'System step completed by operator');
      return;
    }

    // For regular tasks outside of session, open individual SOP modal
    setActiveTasks(prev => 
      prev.map(t => 
        t.Uuid === taskUuid 
          ? { ...t, status: 'in-progress', startedAt: new Date().toISOString() }
          : t
      )
    );

    // Show SOP modal for this task
    const taskToShow = activeTasks.find(t => t.Uuid === taskUuid);
    setShowSOPModal(taskToShow);
  };

  const handleTaskCompletion = (taskUuid, success, notes = '') => {
    const task = activeTasks.find(t => t.Uuid === taskUuid);
    if (!task) return;

    // Send response
    sendTaskResponse(taskUuid, success ? 'SUCCESSFUL' : 'FAILURE', notes);

    // Remove task from active tasks
    setActiveTasks(prev => prev.filter(t => t.Uuid !== taskUuid));

    toast.success(`Task "${task.sopDefinition.title}" ${success ? 'COMPLETED' : 'FAILED'}`);
  };

  const handleInstructionCompletion = (instructionUuid, success, notes = '') => {
    if (!activeSession) return;

    // Send response for the instruction
    sendTaskResponse(instructionUuid, success ? 'SUCCESSFUL' : 'FAILURE', notes);

    // Mark instruction as completed
    setActiveSession(prev => {
      const instruction = prev.instructions.find(inst => inst.Uuid === instructionUuid);
      if (!instruction) {
        console.error('Instruction not found:', instructionUuid);
        return prev;
      }

      const completedInstruction = {
        ...instruction,
        completed: true,
        success: success,
        notes: notes,
        completedAt: new Date().toISOString()
      };

      const newCurrentIndex = prev.currentInstructionIndex + 1;

      return {
        ...prev,
        completedInstructions: [...prev.completedInstructions, completedInstruction],
        currentInstructionIndex: newCurrentIndex
      };
    });

    // Clean instruction completion message
    toast.success(`Instruction "${activeSession.instructions.find(inst => inst.Uuid === instructionUuid)?.sopDefinition.title}" ${success ? 'COMPLETED' : 'FAILED'}`);
  };

  const completeSession = () => {
    if (!activeSession) return;

    // Send session completion response for the sopId 0 message
    if (activeSession.completionMessage) {
      sendTaskResponse(activeSession.completionMessage.Uuid, 'SUCCESSFUL', 'Session completed by operator');
    }

    // Clear session
    setActiveSession(null);
    setShowSOPModal(false);
    
    toast.success('Session completed successfully');
  };

  const cancelSession = () => {
    if (!activeSession) return;

    // Send failure response for completion message if exists
    if (activeSession.completionMessage) {
      sendTaskResponse(activeSession.completionMessage.Uuid, 'FAILURE', 'Session cancelled by operator');
    }

    // Send failure responses for any pending instructions
    const pendingInstructions = activeSession.instructions.slice(activeSession.currentInstructionIndex);
    pendingInstructions.forEach(instruction => {
      if (!activeSession.completedInstructions.find(comp => comp.Uuid === instruction.Uuid)) {
        sendTaskResponse(instruction.Uuid, 'FAILURE', 'CANCELLED');
      }
    });

    // Clear session
    setActiveSession(null);
    setShowSOPModal(false);
    
    toast.warn('Session cancelled');
  };

  const reopenSessionModal = () => {
    if (activeSession) {
      setShowSOPModal(true);
    }
  };

  const getTaskTypeIcon = (task) => {
    if (task.isSystemStep) return '';
    if (task.isSessionStarter) {
      return sopHelpers.getSessionTypeIcon(task.sessionType);
    }
    return '';
  };

  const getTaskTypeLabel = (task) => {
    if (task.isSystemStep) return 'System Step';
    if (task.isSessionStarter) return `${task.sessionType.toUpperCase()} Session`;
    return 'Task';
  };

  const getPriorityColor = (task) => {
    if (task.isSystemStep) return '#3498DB';
    if (task.isSessionStarter) {
      return sopHelpers.getSessionTypeColor(task.sessionType);
    }
    return '#95A5A6';
  };

  return (
    <div className="sop-dashboard">
      <div className="dashboard-header">
        <h1>Operator SOP Dashboard</h1>
        <div className="connection-status">
          <span className={`status-indicator ${mqttConnected ? 'connected' : 'disconnected'}`}></span>
          MQTT: {mqttConnected ? 'Connected' : 'Disconnected'}
        </div>
      </div>

      {!mqttConnected && (
        <div className="warning-banner">
          <p>MQTT Disconnected - Task requests may not be received in real-time</p>
        </div>
      )}

      {activeSession && (
        <div className="session-banner">
          <div className="session-banner-content">
            <div>
              <h3>
                {activeSession.canComplete ? 'Ready to Complete:' : 'Active:'} 
                {activeSession.sessionType.toUpperCase()} Session 
                {!activeSession.canComplete && <span className="loading-spinner">●</span>}
              </h3>
              <p>Session ID: {activeSession.sessionId} | Instructions: {activeSession.instructions.length} | Completed: {activeSession.completedInstructions.length}</p>
              {activeSession.canComplete && (
                <p className="session-ready">All tasks completed - ready for final confirmation</p>
              )}
              {!activeSession.canComplete && (
                <p className="session-in-progress">Session in progress - waiting for more instructions</p>
              )}
            </div>
            {!showSOPModal && (
              <button className="reopen-session-btn" onClick={reopenSessionModal}>
                Open Session
              </button>
            )}
          </div>
        </div>
      )}

      <div className="tasks-container">
        <h2>Active Tasks ({activeTasks.length})</h2>
        
        {activeTasks.length === 0 && !activeSession ? (
          <div className="no-tasks">
            <p>No active tasks at this time</p>
            <p>Tasks will appear here when received via MQTT</p>
            <div className="demo-buttons-grid">
              <button 
                className="demo-button"
                onClick={() => handleTaskReceived({
                  Uuid: `demo-filling-${Date.now()}`,
                  SopId: 10
                })}
              >
                Add Demo Filling Session
              </button>
              <button 
                className="demo-button"
                onClick={() => handleTaskReceived({
                  Uuid: `demo-stoppering-${Date.now()}`,
                  SopId: 20
                })}
              >
                Add Demo Stoppering Session
              </button>
              <button 
                className="demo-button"
                onClick={() => handleTaskReceived({
                  Uuid: `demo-subtask-${Date.now()}`,
                  SopId: 11
                })}
              >
                Add Demo Subtask (will be rejected - no session)
              </button>
            </div>
          </div>
        ) : activeTasks.length === 0 && activeSession ? (
          <div className="no-tasks">
            <p>{activeSession.sessionType.toUpperCase()} session is active - instructions will appear in the modal</p>
            <div className="demo-buttons-grid">
              <button 
                className="demo-button"
                onClick={() => {
                  const baseId = activeSession.sessionStarterId;
                  handleTaskReceived({
                    Uuid: `demo-instruction-${Date.now()}`,
                    SopId: baseId + 1
                  });
                }}
              >
                Add Demo Instruction ({activeSession.sessionStarterId + 1})
              </button>
              <button 
                className="demo-button"
                onClick={() => {
                  const baseId = activeSession.sessionStarterId;
                  handleTaskReceived({
                    Uuid: `demo-instruction-${Date.now()}`,
                    SopId: baseId + 2
                  });
                }}
              >
                Add Demo Instruction ({activeSession.sessionStarterId + 2})
              </button>
              <button 
                className="demo-button"
                onClick={() => handleTaskReceived({
                  Uuid: `demo-complete-${Date.now()}`,
                  SopId: 0
                })}
              >
                Send Demo Complete (SopId 0)
              </button>
              <button 
                className="demo-button"
                onClick={() => handleTaskReceived({
                  Uuid: `demo-wrong-task-${Date.now()}`,
                  SopId: 21
                })}
              >
                Add Wrong Session Task (will be rejected)
              </button>
            </div>
          </div>
        ) : (
          <div className="tasks-list">
            {activeTasks.map(task => (
              <div key={task.Uuid} className="task-card">
                <div className="task-header">
                  <div className="task-title">
                    <h3>
                      {getTaskTypeIcon(task)} {task.sopDefinition.title}
                    </h3>
                    <div className="task-meta">
                      <span 
                        className="task-type-badge"
                        style={{ backgroundColor: getPriorityColor(task) }}
                      >
                        {getTaskTypeLabel(task)}
                      </span>
                      <span className="sop-id-badge">
                        SOP ID: {task.SopId}
                      </span>
                      {task.Acknowledged && (
                        <span className="acknowledged-badge">
                          Acknowledged
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="task-timestamp">
                    {new Date(task.TimeStamp).toLocaleString()}
                  </div>
                </div>
                
                <div className="task-details">
                  <p><strong>Description:</strong> {task.sopDefinition.description}</p>
                  <p><strong>UUID:</strong> {task.Uuid}</p>
                  {task.sessionType && (
                    <p><strong>Session Type:</strong> {task.sessionType}</p>
                  )}
                  {task.AcknowledgedAt && (
                    <p><strong>Acknowledged:</strong> {new Date(task.AcknowledgedAt).toLocaleString()}</p>
                  )}
                </div>

                <div className="task-actions">
                  {task.isSessionStarter && task.Status === 'pending' && (
                    <div className="session-actions">
                      <button 
                        className="acknowledge-btn"
                        onClick={() => acknowledgeTask(task.Uuid)}
                        disabled={task.Acknowledged || (activeSession && activeSession.sessionStarterId !== task.SopId)}
                      >
                        {task.Acknowledged ? 'Acknowledged' : 'Acknowledge'}
                      </button>
                      <button 
                        className="start-session-btn"
                        onClick={() => startSession(task.Uuid)}
                        disabled={!task.Acknowledged || activeSession}
                      >
                        Start Session
                      </button>
                    </div>
                  )}
                  
                  {!task.isSessionStarter && task.Status === 'pending' && (
                    <button 
                      className="execute-btn"
                      onClick={() => executeTask(task.Uuid)}
                      disabled={activeSession}
                    >
                      {task.isSystemStep ? 'Execute' : 'Start Task'}
                    </button>
                  )}
                  
                  {task.Status === 'in-progress' && !task.isSystemStep && !task.isSessionStarter && (
                    <div className="task-progress-actions">
                      <span className="in-progress-text">Task in progress...</span>
                      <button 
                        className="reopen-task-btn"
                        onClick={() => setShowSOPModal(true)}
                      >
                        Open Task
                      </button>
                    </div>
                  )}
                  
                  {activeSession && !task.isSessionStarter && task.Status === 'pending' && (
                    <span className="blocked-text">Session active - task blocked</span>
                  )}
                  
                  {activeSession && task.isSessionStarter && task.Status === 'pending' && !task.Acknowledged && (
                    <span className="queued-text">Queued - complete current session first</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showSOPModal && activeSession && (
        <SOPModal
          session={activeSession}
          onInstructionComplete={handleInstructionCompletion}
          onSessionComplete={completeSession}
          onCancel={cancelSession}
        />
      )}

      {showSOPModal && !activeSession && (
        <SOPModal
          task={activeTasks.find(t => t.status === 'in-progress')}
          onComplete={(success, notes) => {
            const task = activeTasks.find(t => t.status === 'in-progress');
            if (task) {
              handleTaskCompletion(task.Uuid, success, notes);
              setShowSOPModal(false);
            }
          }}
          onCancel={() => {
            setShowSOPModal(false);
            setActiveTasks(prev => 
              prev.map(t => 
                t.status === 'in-progress'
                  ? { ...t, status: 'pending' }
                  : t
              )
            );
          }}
        />
      )}
    </div>
  );
}