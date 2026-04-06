from enum import Enum


class ProfileType(str, Enum):
    P1 = "P1"  # família com bebês/crianças pequenas (0-5)
    P2 = "P2"  # família mista com crianças em idade escolar (6-12)
    P3 = "P3"  # grupo com adolescentes (13-17)
    P4 = "P4"  # adultos foco nos ícones
    P5 = "P5"  # ritmo leve e tranquilo
    P6 = "P6"  # família multigeracional
    P7 = "P7"  # adultos, adrenalina máxima
