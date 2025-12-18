import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import React, { useEffect, useState, useRef } from "react";
import "./Task.css";

export const Task = ({ 
  id, 
  title, 
  color = "#ffffff", 
  isTemplate = false,
  inSidebar = false,
  isNew = false,
  isDraggingToDelete = false,
  onDelete = null,
  nodeData = null  // Add nodeData prop for AAS metadata
}) => {
  // Use ref instead of state for more direct DOM manipulation
  const taskRef = useRef(null);
  const [animating, setAnimating] = useState(false);
  
  // Use a more direct approach to trigger animation
  useEffect(() => {
    if (isNew && taskRef.current && !inSidebar) {
      console.log(`Starting animation for task ${id}`);
      
      // Force browser to recalculate styles
      window.requestAnimationFrame(() => {
        setAnimating(true);
        
        // Log to confirm class application
        console.log(`Applied animation class to task ${id}`);
        console.log(`Element classes: ${taskRef.current.className}`);
        
        // Set timeout to match animation duration
        const timer = setTimeout(() => {
          setAnimating(false);
          console.log(`Animation ended for task ${id}`);
        }, 2000); // 2 seconds to match CSS
        
        return () => clearTimeout(timer);
      });
    }
  }, [isNew, id, inSidebar]);

  const { attributes, listeners, setNodeRef, transform } = useDraggable({
    id,
  });
  
  // Combine refs
  const setRefs = (element) => {
    taskRef.current = element;
    setNodeRef(element);
  };

  const style = {
    transform: CSS.Translate.toString(transform),
    backgroundColor: color,
    color: getContrastColor(color),
  };

  const showDeleteButton = !isTemplate && !inSidebar && onDelete;

  function getContrastColor(hexColor) {
    // Convert hex to RGB
    const r = parseInt(hexColor.substring(1, 3), 16);
    const g = parseInt(hexColor.substring(3, 5), 16);
    const b = parseInt(hexColor.substring(5, 7), 16);
    
    // Calculate brightness (YIQ formula)
    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
    
    // Return black for light backgrounds, white for dark backgrounds
    return brightness > 128 ? '#222222' : '#ffffff';
  }

  const handleDeleteClick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (onDelete) {
      onDelete(id);
    }
  };

  const classNames = [
    "task",
    isTemplate ? "task-template" : "",
    animating ? "task-new" : "",
    isDraggingToDelete ? "dragging-to-delete" : ""  // Add this class
  ].filter(Boolean).join(" ");

  // Log class application
  if (animating) {
    console.log(`Task ${id} has animation class applied`);
  }

  // Build tooltip content from nodeData
  const getTooltipContent = () => {
    if (!nodeData) return null;
    
    const parts = [];
    if (nodeData.assetType) parts.push(`Type: ${nodeData.assetType}`);
    if (nodeData.assetKind) parts.push(`Kind: ${nodeData.assetKind}`);
    if (nodeData.assetId) parts.push(`Asset ID: ${nodeData.assetId}`);
    if (nodeData.aasId) parts.push(`AAS ID: ${nodeData.aasId}`);
    
    return parts.join('\n');
  };

  // Truncate long IDs for display
  const truncateId = (id, maxLength = 25) => {
    if (!id) return '';
    if (id.length <= maxLength) return id;
    // Show last part after last /
    const parts = id.split('/');
    const lastPart = parts[parts.length - 1];
    if (lastPart.length <= maxLength) return '...' + lastPart;
    return '...' + lastPart.substring(lastPart.length - maxLength);
  };

  return (
    <div
      ref={setRefs}
      style={style}
      {...attributes}
      {...listeners}
      className={classNames}
      data-animating={animating ? "true" : "false"}
      data-id={id}
      title={nodeData ? getTooltipContent() : undefined}
    >
      <div className="task-content">
        <div className="task-title">{title}</div>
        {nodeData && (
          <div className="task-metadata">
            {nodeData.assetType && (
              <div className="task-meta-item asset-type">
                <span className="meta-label">Type:</span> 
                <span className="meta-value">{nodeData.assetType}</span>
              </div>
            )}
            {nodeData.assetKind && (
              <div className="task-meta-item asset-kind">
                <span className="meta-label">Kind:</span> 
                <span className="meta-value">{nodeData.assetKind}</span>
              </div>
            )}
            {nodeData.assetId && (
              <div className="task-meta-item asset-id">
                <span className="meta-label">Asset:</span> 
                <span className="meta-value" title={nodeData.assetId}>{truncateId(nodeData.assetId)}</span>
              </div>
            )}
            {nodeData.aasId && (
              <div className="task-meta-item aas-id">
                <span className="meta-label">AAS:</span> 
                <span className="meta-value" title={nodeData.aasId}>{truncateId(nodeData.aasId)}</span>
              </div>
            )}
          </div>
        )}
      </div>
      
      {showDeleteButton && (
        <button 
          className="delete-task-btn" 
          onClick={handleDeleteClick}
          onMouseDown={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
          aria-label="Delete task"
        >
          ×
        </button>
      )}
    </div>
  );
};