import React from 'react';
import { getBezierPath, BaseEdge } from 'reactflow';

const FloralEdge = ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style }) => {
    const [edgePath] = getBezierPath({
        sourceX, sourceY, sourcePosition,
        targetX, targetY, targetPosition,
        curvature: 0.3,
    });
    return <BaseEdge id={id} path={edgePath} style={{ ...style, strokeOpacity: 0.6 }} />;
};

export default FloralEdge;