export const sopDefinitions = {
  // System steps
  0: {
    title: 'Complete Session',
    description: 'Signal that all session tasks are complete and ready for operator confirmation',
    instructions: [
      'All session instructions have been processed',
      'Review any notes or issues from the session',
      'Confirm session completion when ready'
    ],
    isSystemStep: true,
    isSessionCompleter: true
  },
  // Filling process (10-19)
  10: {
    title: 'Start Filling Session',
    description: 'Begin filling process session',
    instructions: [
      'Prepare workspace for filling operations',
      'Ensure all safety protocols are in place',
      'Verify filling equipment is ready'
    ],
    isSessionStarter: true,
    sessionType: 'filling'
  },
  11: {
    title: 'Prepare Filling Station',
    description: 'Set up and prepare the filling station',
    instructions: [
      'Check that all vials are properly positioned',
      'Verify filling nozzles are clean and unobstructed',
      'Confirm liquid supply is adequate',
      'Verify temperature settings are correct'
    ]
  },
  12: {
    title: 'Start Filling Process',
    description: 'Begin the automated filling sequence',
    instructions: [
      'Press the green START button on the filling station',
      'Monitor the first few vials for proper fill level',
      'Verify no leaks or spills occur',
      'Check filling speed is within specifications'
    ]
  },
  13: {
    title: 'Quality Check - Fill Level',
    description: 'Perform quality inspection on filled vials',
    instructions: [
      'Check fill levels match specification (±2%)',
      'Inspect for contamination or defects',
      'Document any issues found',
      'Take sample measurements if required'
    ]
  },

  // Stoppering process (20-29)
  20: {
    title: 'Start Stoppering Session',
    description: 'Begin stoppering process session',
    instructions: [
      'Prepare workspace for stoppering operations',
      'Ensure pneumatic systems are ready',
      'Verify stopper supply is adequate'
    ],
    isSessionStarter: true,
    sessionType: 'stoppering'
  },
  21: {
    title: 'Prepare Stoppering Station',
    description: 'Set up station for stopper insertion',
    instructions: [
      'Load stoppers into the feeding mechanism',
      'Verify stopper orientation is correct',
      'Check pneumatic pressure levels (6-8 bar)',
      'Test stopper insertion mechanism'
    ]
  },
  22: {
    title: 'Execute Stoppering',
    description: 'Begin stopper insertion process',
    instructions: [
      'Initiate stoppering sequence',
      'Monitor for proper stopper placement',
      'Ensure no damaged stoppers are used',
      'Verify seal integrity'
    ]
  },
  23: {
    title: 'Stopper Quality Check',
    description: 'Inspect stopper placement and seal quality',
    instructions: [
      'Check stopper insertion depth',
      'Verify no damaged or misaligned stoppers',
      'Test seal integrity on sample vials',
      'Document any defects found'
    ]
  },

  // Capping process (30-39)
  30: {
    title: 'Start Capping Session',
    description: 'Begin capping process session',
    instructions: [
      'Prepare workspace for capping operations',
      'Ensure cap supply is ready',
      'Verify capping equipment functionality'
    ],
    isSessionStarter: true,
    sessionType: 'capping'
  },
  31: {
    title: 'Prepare Capping Station',
    description: 'Set up station for cap application',
    instructions: [
      'Load caps into the feeding system',
      'Verify cap orientation and alignment',
      'Check torque settings for cap application',
      'Test capping mechanism operation'
    ]
  },
  32: {
    title: 'Execute Capping',
    description: 'Apply caps to vials',
    instructions: [
      'Initiate capping sequence',
      'Monitor cap application for proper torque',
      'Verify caps are properly seated',
      'Check for any damaged caps'
    ]
  },

  // RTU Tubs handling (40-49)
  40: {
    title: 'Start RTU Tubs Session',
    description: 'Begin RTU tubs handling session',
    instructions: [
      'Prepare workspace for RTU tub operations',
      'Ensure tub supply is ready',
      'Verify handling equipment is operational'
    ],
    isSessionStarter: true,
    sessionType: 'rtu-tubs'
  },
  41: {
    title: 'Prepare RTU Tub Station',
    description: 'Set up for RTU tub handling',
    instructions: [
      'Load empty RTU tubs into position',
      'Verify tub orientation and alignment',
      'Check labeling system is ready',
      'Confirm transfer mechanism is operational'
    ]
  },
  42: {
    title: 'Load Vials into RTU Tubs',
    description: 'Transfer vials into RTU tubs',
    instructions: [
      'Initiate vial transfer sequence',
      'Monitor vial placement in tubs',
      'Verify proper vial orientation',
      'Check for any damaged vials during transfer'
    ]
  },

  // Labeling process (50-59)
  50: {
    title: 'Start Labeling Session',
    description: 'Begin labeling process session',
    instructions: [
      'Prepare workspace for labeling operations',
      'Ensure label stock is loaded',
      'Verify printer functionality'
    ],
    isSessionStarter: true,
    sessionType: 'labeling'
  },
  51: {
    title: 'Prepare Labeling Station',
    description: 'Set up labeling equipment',
    instructions: [
      'Load label stock into applicator',
      'Verify label alignment',
      'Check print quality settings',
      'Test label adhesion'
    ]
  },
  52: {
    title: 'Execute Labeling',
    description: 'Apply labels to vials/containers',
    instructions: [
      'Initiate labeling sequence',
      'Monitor label placement accuracy',
      'Verify print quality and readability',
      'Check for wrinkles or air bubbles'
    ]
  },

  // Inspection process (60-69)
  60: {
    title: 'Start Inspection Session',
    description: 'Begin quality inspection session',
    instructions: [
      'Prepare workspace for inspection',
      'Ensure inspection equipment is calibrated',
      'Set up documentation system'
    ],
    isSessionStarter: true,
    sessionType: 'inspection'
  },
  61: {
    title: 'Visual Inspection',
    description: 'Perform visual quality checks',
    instructions: [
      'Inspect containers for defects',
      'Check label placement and quality',
      'Verify fill levels and color',
      'Document any non-conformities'
    ]
  },
  62: {
    title: 'Dimensional Inspection',
    description: 'Measure critical dimensions',
    instructions: [
      'Measure container dimensions',
      'Check stopper insertion depth',
      'Verify cap torque values',
      'Record measurements in system'
    ]
  }
};

// Helper functions for SOP operations
export const sopHelpers = {
  isSessionStarter: (sopId) => {
    return sopId % 10 === 0 && sopId >= 10 && sopId <= 90;
  },

  isSessionCompleter: (sopId) => {
    return sopId === 0;
  },

  getSessionType: (sopId) => {
    const sessionStarter = Math.floor(sopId / 10) * 10;
    const sessionDef = sopDefinitions[sessionStarter];
    return sessionDef ? sessionDef.sessionType : 'unknown';
  },

  isSubtaskOf: (sopId, sessionStarterId) => {
    return Math.floor(sopId / 10) === Math.floor(sessionStarterId / 10) && sopId !== sessionStarterId;
  },

  getSessionStarter: (sopId) => {
    return Math.floor(sopId / 10) * 10;
  },

  getSubtasks: (sessionStarterId) => {
    const subtasks = [];
    for (let i = sessionStarterId + 1; i < sessionStarterId + 10; i++) {
      if (sopDefinitions[i]) {
        subtasks.push({ sopId: i, ...sopDefinitions[i] });
      }
    }
    return subtasks;
  },

  getAllSessionStarters: () => {
    return Object.keys(sopDefinitions)
      .map(Number)
      .filter(sopId => sopHelpers.isSessionStarter(sopId))
      .map(sopId => ({ sopId, ...sopDefinitions[sopId] }));
  },

  getSessionTypeColor: (sessionType) => {
    const colors = {
      filling: '#E74C3C',
      stoppering: '#F39C12',
      capping: '#9B59B6',
      'rtu-tubs': '#1ABC9C',
      labeling: '#3498DB',
      inspection: '#2ECC71'
    };
    return colors[sessionType] || '#34495E';
  },

  getSessionTypeIcon: (sessionType) => {
    const icons = {
      filling: '🧪',
      stoppering: '🔌',
      capping: '🎩',
      'rtu-tubs': '📦',
      labeling: '🏷️',
      inspection: '🔍'
    };
    return icons[sessionType] || '🔄';
  }
};