# -*- coding: utf-8 -*-
"""
Grilla sistemática con arranque aleatorio
Script de Procesos para QGIS 3.x

Genera una grilla regular de puntos dentro de un polígono, con el origen
sorteado al azar dentro de una celda. Cada ejecución produce una grilla
distinta; indicando una semilla se puede reproducir una grilla anterior.
"""

import math
import random

import processing
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorDestination,
    QgsProcessingUtils,
)


class GrillaSistematicaAleatoria(QgsProcessingAlgorithm):

    INPUT = 'INPUT'
    DISTANCIA = 'DISTANCIA'
    N_PARCELAS = 'N_PARCELAS'
    SEMILLA = 'SEMILLA'
    OUTPUT = 'OUTPUT'

    # ---------- Metadatos ----------
    def name(self):
        return 'grilla_sistematica_aleatoria'

    def displayName(self):
        return 'Grilla sistemática con arranque aleatorio'

    def group(self):
        return 'RGM Forest Tools'

    def groupId(self):
        return 'rgmforesttools'

    def shortHelpString(self):
        return (
            '<p>Genera una grilla regular de parcelas (puntos) dentro del área de '
            'estudio. El punto de arranque se sortea dentro de una celda, de modo '
            'que cada ejecución produce una grilla en otra posición, manteniendo '
            'la equidistancia (muestreo sistemático con arranque aleatorio).</p>'
            '<p><b>Completar solo uno</b>: la equidistancia entre parcelas o el '
            'número de parcelas. En el segundo caso la equidistancia se calcula '
            'como √(área / n), por lo que el número final es aproximado.</p>'
            '<p><b>Semilla</b>: dejarla vacía para obtener una grilla nueva en cada '
            'ejecución. La semilla usada se informa en el registro y en el nombre '
            'de la capa; ingresándola de nuevo se reproduce la misma grilla.</p>'
            '<p>La capa debe estar en un SRC proyectado (metros).</p>'
        )

    def createInstance(self):
        return GrillaSistematicaAleatoria()

    # ---------- Parámetros ----------
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT, 'Área de estudio',
            [QgsProcessing.TypeVectorPolygon]))

        self.addParameter(QgsProcessingParameterNumber(
            self.DISTANCIA, 'Equidistancia entre parcelas (m)',
            type=QgsProcessingParameterNumber.Double,
            optional=True, minValue=0))

        self.addParameter(QgsProcessingParameterNumber(
            self.N_PARCELAS, 'Número de parcelas',
            type=QgsProcessingParameterNumber.Integer,
            optional=True, minValue=0))

        self.addParameter(QgsProcessingParameterNumber(
            self.SEMILLA, 'Semilla (vacío = grilla nueva)',
            type=QgsProcessingParameterNumber.Integer,
            optional=True, minValue=0))

        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT, 'Grilla sistemática'))

    def _opcional(self, parameters, nombre, context):
        """Devuelve el valor numérico del parámetro o None si quedó vacío o en 0."""
        valor = parameters.get(nombre)
        if valor is None or valor == '':
            return None
        valor = self.parameterAsDouble(parameters, nombre, context)
        return valor if valor > 0 else None

    # ---------- Proceso ----------
    def processAlgorithm(self, parameters, context, feedback):
        fuente = self.parameterAsSource(parameters, self.INPUT, context)
        if fuente is None:
            raise QgsProcessingException('No se pudo leer la capa de área de estudio.')

        crs = fuente.sourceCrs()
        if crs.isGeographic():
            raise QgsProcessingException(
                'La capa está en un SRC geográfico (grados). '
                'Reproyectala a un SRC proyectado en metros antes de continuar.')

        d = self._opcional(parameters, self.DISTANCIA, context)
        n = self._opcional(parameters, self.N_PARCELAS, context)

        if (d is None) == (n is None):
            raise QgsProcessingException(
                'Completá solo uno de los dos campos: equidistancia o número de parcelas.')

        if n is not None:
            area = sum(f.geometry().area() for f in fuente.getFeatures())
            d = math.sqrt(area / n)
            feedback.pushInfo(f'Área total: {area / 10000:.2f} ha → equidistancia calculada: {d:.1f} m')

        semilla = self._opcional(parameters, self.SEMILLA, context)
        semilla = int(semilla) if semilla is not None else random.randrange(1_000_000)
        rng = random.Random(semilla)

        dx = rng.uniform(0, d)
        dy = rng.uniform(0, d)

        # Extensión trasladada (-dx, -dy) y ampliada en d para cubrir toda el área
        ext = fuente.sourceExtent()
        extension = (f'{ext.xMinimum() - dx},{ext.xMaximum() - dx + d},'
                     f'{ext.yMinimum() - dy},{ext.yMaximum() - dy + d} '
                     f'[{crs.authid()}]')

        grilla = processing.run('native:creategrid', {
            'TYPE': 0,
            'EXTENT': extension,
            'HSPACING': d, 'VSPACING': d,
            'HOVERLAY': 0, 'VOVERLAY': 0,
            'CRS': crs,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        }, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        if feedback.isCanceled():
            return {}

        resultado = processing.run('native:clip', {
            'INPUT': grilla,
            'OVERLAY': parameters[self.INPUT],
            'OUTPUT': parameters[self.OUTPUT],
        }, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']

        capa = QgsProcessingUtils.mapLayerFromString(resultado, context)
        cantidad = capa.featureCount() if capa else '?'

        feedback.pushInfo(
            f'Semilla: {semilla} | d = {d:.1f} m | dx = {dx:.1f} m | dy = {dy:.1f} m | '
            f'parcelas generadas: {cantidad}')

        if context.willLoadLayerOnCompletion(resultado):
            context.layerToLoadOnCompletionDetails(resultado).name = (
                f'Grilla semilla {semilla} (d = {d:.0f} m)')

        return {self.OUTPUT: resultado}
