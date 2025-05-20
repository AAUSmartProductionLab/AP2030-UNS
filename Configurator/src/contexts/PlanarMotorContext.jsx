import React, { createContext, useState, useContext, useEffect } from 'react';

const PlanarMotorContext = createContext();

export const usePlanarMotorContext = () => useContext(PlanarMotorContext);

export const PlanarMotorProvider = ({ children }) => {
  // Get saved nodes from localStorage
  const [placedNodes, setPlacedNodes] = useState(() => {
    try {
      const savedNodes = localStorage.getItem('planarMotorNodes');
      return savedNodes ? JSON.parse(savedNodes) : [];
    } catch (error) {
      console.error('Error loading nodes from localStorage:', error);
      return [];
    }
  });

  // Share the nodes with any component that needs them
  const value = {
    placedNodes,
    setPlacedNodes
  };

  return (
    <PlanarMotorContext.Provider value={value}>
      {children}
    </PlanarMotorContext.Provider>
  );
};