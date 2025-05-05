import React from 'react';
import { 
  DndContext, 
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  arrayMove,
  verticalListSortingStrategy
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import './BatchSidebar.css';

export const BatchSidebar = ({ queue, setQueue, log, setLog, onRemoveBatch }) => {
    const handleStartBatch = (batchId) => {
        // Find the batch in the queue
        const batchToStart = queue.find(batch => batch.id === batchId);
        
        if (batchToStart) {
            // Create a log entry
            const logEntry = {
                id: `log-${Date.now()}`,
                name: batchToStart.name,
                product: batchToStart.product,
                completedDate: new Date().toISOString().slice(0, 10), // Current date in YYYY-MM-DD format
                status: 'Completed'
            };
            
            // Add to log
            setLog(prevLog => [...prevLog, logEntry]);
            
            // Remove from queue
            onRemoveBatch(batchId);
        }
    };
    
    // Component for a single queue item
    const QueueItem = ({ batch }) => {
        const isRunning = batch.status === 'Running';
        
        const {
            attributes,
            listeners,
            setNodeRef,
            transform,
            transition,
            isDragging
        } = useSortable({ 
            id: batch.id,
            disabled: isRunning // Disable dragging for running batches
        });

        const style = {
            transform: CSS.Transform.toString(transform),
            transition,
            // Add a cursor style for running batches
            cursor: isRunning ? 'not-allowed' : 'grab'
        };
        
        const handleRemoveClick = (e) => {
            // Stop event propagation to prevent drag handlers from capturing it
            e.stopPropagation();
            e.preventDefault();
            onRemoveBatch(batch.id);
        };
        
        const handleStartClick = (e) => {
            // Stop event propagation to prevent drag handlers from capturing it
            e.stopPropagation();
            e.preventDefault();
            handleStartBatch(batch.id);
        };

        return (
            <div 
                ref={setNodeRef}
                style={style}
                className={`queue-item ${isRunning ? 'running' : ''} ${isDragging ? 'dragging' : ''}`}
                {...attributes}
                {...(isRunning ? {} : listeners)} // Only add listeners if not running
            >
                <div className="queue-item-header">
                    <h4>{batch.name}</h4>
                    <span className={`queue-item-status ${batch.status.toLowerCase()}`}>
                        {batch.status}
                    </span>
                </div>
                <div className="queue-item-details">
                    <div className="detail-row">
                        <span className="detail-label">Product:</span>
                        <span className="detail-value">{batch.product}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">Units:</span>
                        <span className="detail-value">{batch.volume}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">Packaging:</span>
                        <span className="detail-value">{batch.packaging}</span>
                    </div>
                </div>
                <div className="queue-item-actions">
                    <button className="queue-action-btn start"
                            onClick={handleStartClick}
                            disabled={isRunning} // Disable start button for running batches
                    >
                        {isRunning ? "Running" : "Start"}
                    </button>
                    <button 
                        className="queue-action-btn remove"
                        onClick={handleRemoveClick}
                    >
                        Remove
                    </button>
                </div>
                
                {/* Optional: Add a running indicator for visual feedback */}
                {isRunning && (
                    <div className="running-indicator">
                        <span className="running-icon">⚙️</span>
                    </div>
                )}
            </div>
        );
    };

    // LogItem component remains unchanged
    const LogItem = ({ batch }) => {
        // ... existing implementation
        return (
            <div className="log-item">
                {/* Existing LogItem content */}
                <div className="log-item-header">
                    <h4>{batch.name}</h4>
                    <span className={`log-item-status ${batch.status.toLowerCase()}`}>
                        {batch.status}
                    </span>
                </div>
                <div className="log-item-details">
                    <div className="detail-row">
                        <span className="detail-label">Product:</span>
                        <span className="detail-value">{batch.product}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">Completed:</span>
                        <span className="detail-value">{batch.completedDate}</span>
                    </div>
                </div>
            </div>
        );
    };

    // Set up sensors for drag and drop
    const sensors = useSensors(
        useSensor(PointerSensor, {
            // Increase activation distance to make it less likely to trigger accidentally
            activationConstraint: {
                distance: 10, // 10px of movement before drag starts
            },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    // Modified handleDragEnd to prevent reordering running batches
    const handleDragEnd = (event) => {
        const { active, over } = event;
        
        // If no over target, or same item, do nothing
        if (!over || active.id === over.id) {
            return;
        }
        
        // Find the dragged batch and destination batch
        const draggedBatch = queue.find(batch => batch.id === active.id);
        const targetBatch = queue.find(batch => batch.id === over.id);
        
        // Check if the dragged batch or target is running
        if (draggedBatch.status === 'Running') {
            // Don't allow dragging a running batch
            return;
        }
        
        // Check if we're trying to reorder items to place before a running item at position 0
        const oldIndex = queue.findIndex(item => item.id === active.id);
        const newIndex = queue.findIndex(item => item.id === over.id);
        
        // If trying to place an item at position 0 and there's a running order at position 0, prevent it
        if (newIndex === 0 && queue[0].status === 'Running' && oldIndex !== 0) {
            return;
        }
        
        // Otherwise, allow the reordering
        setQueue((items) => {
            return arrayMove(items, oldIndex, newIndex);
        });
    };

    return (
        <div className="sidebar-container">
            <div className="sidebar-section">
                <div className="section-header">
                    <h2>Batch Queue</h2>
                    <span className="item-count">{queue.length} batches</span>
                </div>
                <DndContext 
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragEnd={handleDragEnd}
                >
                    <SortableContext 
                        items={queue.map(batch => batch.id)}
                        strategy={verticalListSortingStrategy}
                    >
                        <div className="queue-list">
                            {queue.length > 0 ? (
                                queue.map(batch => (
                                    <QueueItem key={batch.id} batch={batch} />
                                ))
                            ) : (
                                <div className="empty-queue-message">
                                    No batches in queue
                                </div>
                            )}
                        </div>
                    </SortableContext>
                </DndContext>
            </div>
            
            <div className="sidebar-section">
                <div className="section-header">
                    <h2>Batch Log</h2>
                    <span className="item-count">{log.length} completed</span>
                </div>
                <div className="log-list">
                    {log.map(batch => (
                        <LogItem key={batch.id} batch={batch} />
                    ))}
                </div>
            </div>
        </div>
    );
}