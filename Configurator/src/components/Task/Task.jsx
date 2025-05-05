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
  isDraggingToDelete = false,  // Add this prop
  onDelete = null 
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

  return (
    <div
      ref={setRefs}
      style={style}
      {...attributes}
      {...listeners}
      className={classNames}
      data-animating={animating ? "true" : "false"}
      data-id={id}
    >
      {title}
      
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