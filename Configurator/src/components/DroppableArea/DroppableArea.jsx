import { useDroppable } from "@dnd-kit/core";
import React from "react";
import "./DroppableArea.css";

export const DroppableArea = ({ 
  id, 
  children, 
  isBlack = false, 
  isCorner = false,
  name = ""
}) => {
  const { isOver, setNodeRef } = useDroppable({
    id,
  });

  // Check if there are any children (tasks)
  const hasChildren = React.Children.count(children) > 0;

  const classNames = [
    "droppable-area",
    isBlack && "black",
    isCorner && "corner",
    isOver && "over",
    hasChildren && "has-task" // Add class when it has a task
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div ref={setNodeRef} className={classNames}>
      {/* Only show title if there's no task */}
      {!hasChildren && <div className="droppable-title">{name}</div>}
      <div className="droppable-content">
        {children}
      </div>
    </div>
  );
};