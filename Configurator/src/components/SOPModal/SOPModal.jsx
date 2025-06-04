import React, { useState } from 'react';
import './SOPModal.css';

export const SOPModal = ({ task, session, onComplete, onInstructionComplete, onSessionComplete, onCancel }) => {
  const [notes, setNotes] = useState('');

  // Handle individual task (non-session)
  if (task && !session) {
    const handleSuccess = () => {
      onComplete(true, notes);
    };

    const handleFailure = () => {
      onComplete(false, notes);
    };

    return (
      <div className="sop-modal-overlay">
        <div className="sop-modal">
          <div className="sop-header">
            <h2>{task.sopDefinition.title}</h2>
            <div className="task-info">
              <span className="sop-id">SOP ID: {task.SopId}</span>
              <span className="task-uuid">UUID: {task.Uuid}</span>
            </div>
            <button className="close-btn" onClick={onCancel}>×</button>
          </div>

          <div className="sop-content">
            <div className="task-description">
              <h3>Task Description</h3>
              <p>{task.sopDefinition.description}</p>
            </div>

            <div className="instructions-section">
              <h4>Instructions:</h4>
              <ol className="instructions-list">
                {task.sopDefinition.instructions.map((instruction, index) => (
                  <li key={index} className="instruction-item">
                    {instruction}
                  </li>
                ))}
              </ol>
            </div>

            <div className="task-notes">
              <h4>Notes (optional):</h4>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add any observations, issues, or notes about this task..."
                rows={4}
              />
            </div>
          </div>

          <div className="sop-actions">
            <div className="cancel-button">
              <button className="cancel-btn" onClick={onCancel}>
                Cancel Task
              </button>
            </div>
            
            <div className="result-buttons">
              <button className="failure-btn" onClick={handleFailure}>
                Mark as Failed
              </button>
              <button className="success-btn" onClick={handleSuccess}>
                Mark as Completed
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Handle session
  if (session) {
    const currentInstruction = session.instructions[session.currentInstructionIndex];
    const hasInstructions = session.instructions.length > 0;
    const allInstructionsCompleted = session.currentInstructionIndex >= session.instructions.length;
    
    const handleInstructionSuccess = () => {
      if (currentInstruction) {
        onInstructionComplete(currentInstruction.Uuid, true, notes);
        setNotes(''); // Clear notes after completion
      }
    };

    const handleInstructionFailure = () => {
      if (currentInstruction) {
        onInstructionComplete(currentInstruction.Uuid, false, notes);
        setNotes(''); // Clear notes after completion
      }
    };

    return (
      <div className="sop-modal-overlay">
        <div className="sop-modal session-modal">
          <div className="sop-header">
            <h2>
              {session.sessionType.toUpperCase()} Session
              {session.canComplete && <span className="completion-indicator">READY</span>}
              {!session.canComplete && <span className="loading-indicator">IN PROGRESS</span>}
            </h2>
            <div className="session-info">
              <span className="session-id">Session ID: {session.sessionId}</span>
              <span className="session-progress">
                Progress: {session.completedInstructions.length} / {session.instructions.length}
              </span>
            </div>
            <button className="close-btn" onClick={onCancel}>×</button>
          </div>

          <div className="sop-content">
            {/* Session completion button when ready */}
            {session.canComplete && (
              <div className="session-completion-section">
                <div className="completion-message">
                  <h3>Session Ready for Completion</h3>
                  <p>All instructions have been processed successfully. Click below to complete the session.</p>
                </div>
                <button className="complete-session-btn" onClick={onSessionComplete}>
                  Complete Session
                </button>
              </div>
            )}

            {/* Current instruction display */}
            {!session.canComplete && hasInstructions && currentInstruction && (
              <>
                <div className="current-instruction">
                  <h3>Current Instruction ({session.currentInstructionIndex + 1} of {session.instructions.length})</h3>
                  <h4>{currentInstruction.sopDefinition.title}</h4>
                  <p>{currentInstruction.sopDefinition.description}</p>
                </div>

                <div className="instructions-section">
                  <h4>Steps:</h4>
                  <ol className="instructions-list">
                    {currentInstruction.sopDefinition.instructions.map((instruction, index) => (
                      <li key={index} className="instruction-item">
                        {instruction}
                      </li>
                    ))}
                  </ol>
                </div>

                <div className="task-notes">
                  <h4>Notes for this instruction (optional):</h4>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Add any observations, issues, or notes about this instruction..."
                    rows={3}
                  />
                </div>
              </>
            )}

            {/* Waiting for instructions */}
            {!session.canComplete && (!hasInstructions || allInstructionsCompleted) && (
              <div className="waiting-instructions">
                <div className="loading-spinner-large">●</div>
                <h3>Waiting for Instructions</h3>
                <p>
                  {!hasInstructions 
                    ? "No instructions received yet. Please wait for the system to send tasks."
                    : "All current instructions completed. Waiting for more instructions or session completion signal."
                  }
                </p>
              </div>
            )}

            {/* Completed instructions summary */}
            {session.completedInstructions.length > 0 && (
              <div className="completed-instructions">
                <h4>Completed Instructions ({session.completedInstructions.length})</h4>
                <div className="completed-list">
                  {session.completedInstructions.map((instruction, index) => (
                    <div key={instruction.Uuid} className={`completed-item ${instruction.success ? 'success' : 'failed'}`}>
                      <span className="instruction-title">
                        {instruction.sopDefinition.title}
                      </span>
                      <span className="completion-time">
                        {new Date(instruction.completedAt).toLocaleTimeString()}
                      </span>
                      <span className={`completion-status ${instruction.success ? 'success' : 'failed'}`}>
                        {instruction.success ? 'COMPLETED' : 'FAILED'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="sop-actions">
            <div className="cancel-button">
              <button className="cancel-btn" onClick={onCancel}>
                Cancel Session
              </button>
            </div>
            
            {/* Instruction completion buttons */}
            {!session.canComplete && currentInstruction && (
              <div className="result-buttons">
                <button className="failure-btn" onClick={handleInstructionFailure}>
                  Mark as Failed
                </button>
                <button className="success-btn" onClick={handleInstructionSuccess}>
                  Mark as Completed
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
};