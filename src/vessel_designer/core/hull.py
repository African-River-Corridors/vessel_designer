"""Box barge hull geometry with bottom rakes at bow and stern.

Side view of hull:
                          |  bow
                          |
         -----------------+  <- deck
        /                 |
       /                  |  <- bow rake (bottom slopes up)
      /                   |
-----+--------------------+  <- keel (flat bottom)
     <--- rake_length --->

The rake is a bottom rake: the hull sides remain vertical, but the bottom
slopes upward at the bow (and optionally stern). This is typical for
pushed/ATB barges on inland waterways.
"""

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class HullGeometry:
    """Box barge hull with bottom rakes."""

    loa: float              # Length overall (m)
    beam: float             # Moulded beam (m)
    depth: float            # Moulded depth (m)
    bow_rake_length: float  # Horizontal length of bow rake (m)
    bow_rake_rise: float    # Vertical rise of bow rake (m)
    stern_rake_length: float  # Horizontal length of stern rake (m)
    stern_rake_rise: float  # Vertical rise of stern rake (m)

    @property
    def parallel_length(self) -> float:
        """Length of the parallel midbody (flat-bottom section)."""
        return self.loa - self.bow_rake_length - self.stern_rake_length

    def _rake_volume(self, draft: float, rake_length: float, rake_rise: float) -> float:
        """Displaced volume in one rake section at given draft.

        The bottom slopes linearly from keel (height=0) up to rake_rise
        over the rake_length. At draft T:
        - If T <= rake_rise: submerged rake forms a triangle in profile
          Volume = beam * T^2 * rake_length / (2 * rake_rise)
        - If T > rake_rise: the full rake is submerged plus a rectangular portion
          Volume = beam * rake_length * (T - rake_rise / 2)
        """
        if rake_length <= 0:
            return 0.0
        if draft <= 0:
            return 0.0
        if draft <= rake_rise:
            return self.beam * draft**2 * rake_length / (2.0 * rake_rise)
        else:
            return self.beam * rake_length * (draft - rake_rise / 2.0)

    def _rake_waterplane_length(self, draft: float, rake_length: float, rake_rise: float) -> float:
        """Length of waterplane intersection in one rake section.

        At the waterline, the rake section contributes a length equal to
        the horizontal distance where the bottom is below the waterline.
        """
        if rake_length <= 0:
            return 0.0
        if draft <= 0:
            return 0.0
        if draft >= rake_rise:
            return rake_length
        return draft * rake_length / rake_rise

    def _rake_first_moment_volume(self, draft: float, rake_length: float,
                                   rake_rise: float, x_start: float,
                                   toward_bow: bool) -> float:
        """First moment of rake displaced volume about x_start (for LCB).

        x_start is the x-coordinate where the rake begins (at the keel end).
        toward_bow=True means the rake extends in the positive x direction from x_start.

        Returns moment = integral of x * dV, where dV = beam * h(x) dx
        and h(x) is the submerged depth at position x within the rake.
        """
        if rake_length <= 0 or draft <= 0:
            return 0.0

        # x measured from the flat-bottom end of the rake toward the tip
        # At position x (0 to rake_length), bottom height = x * rake_rise / rake_length
        # Submerged depth at x: d(x) = max(0, draft - x * rake_rise / rake_length)
        # The submerged portion extends from x=0 to x_max = min(rake_length, draft * rake_length / rake_rise)

        x_max = min(rake_length, draft * rake_length / rake_rise) if rake_rise > 0 else rake_length

        # Moment about x_start in global coordinates:
        # If toward_bow: global_x = x_start + x
        # If toward_stern: global_x = x_start - x

        # Integral: beam * integral_0^x_max (draft - x * rake_rise / rake_length) * (x_start +/- x) dx
        # Let a = draft, b = rake_rise / rake_length
        # = beam * integral_0^x_max (a - b*x) * (x_start +/- x) dx

        a = draft
        b = rake_rise / rake_length if rake_length > 0 else 0

        # Expand and integrate:
        # (a - bx)(x_start + sx) where s = +1 (toward_bow) or -1 (toward_stern)
        # = a*x_start + a*s*x - b*x_start*x - b*s*x^2
        # Integral = a*x_start*x_max + a*s*x_max^2/2 - b*x_start*x_max^2/2 - b*s*x_max^3/3

        s = 1.0 if toward_bow else -1.0
        xm = x_max

        moment = self.beam * (
            a * x_start * xm
            + a * s * xm**2 / 2.0
            - b * x_start * xm**2 / 2.0
            - b * s * xm**3 / 3.0
        )
        return moment

    def displaced_volume(self, draft: float) -> float:
        """Total displaced volume at given draft (m^3)."""
        if draft <= 0:
            return 0.0

        # Parallel midbody
        v_mid = self.beam * min(draft, self.depth) * self.parallel_length

        # Bow rake
        v_bow = self._rake_volume(draft, self.bow_rake_length, self.bow_rake_rise)

        # Stern rake
        v_stern = self._rake_volume(draft, self.stern_rake_length, self.stern_rake_rise)

        return v_mid + v_bow + v_stern

    def waterplane_area(self, draft: float) -> float:
        """Waterplane area at given draft (m^2)."""
        if draft <= 0:
            return 0.0

        l_mid = self.parallel_length
        l_bow = self._rake_waterplane_length(draft, self.bow_rake_length, self.bow_rake_rise)
        l_stern = self._rake_waterplane_length(draft, self.stern_rake_length, self.stern_rake_rise)

        return self.beam * (l_mid + l_bow + l_stern)

    def waterplane_length(self, draft: float) -> float:
        """Effective waterplane length at given draft (m)."""
        l_mid = self.parallel_length
        l_bow = self._rake_waterplane_length(draft, self.bow_rake_length, self.bow_rake_rise)
        l_stern = self._rake_waterplane_length(draft, self.stern_rake_length, self.stern_rake_rise)
        return l_mid + l_bow + l_stern

    def waterplane_inertia_transverse(self, draft: float) -> float:
        """Second moment of waterplane area about the centerline (m^4).

        For a rectangular waterplane: I_T = (1/12) * L_wp * B^3
        This is exact for a box barge since the waterplane is always
        full beam (rakes are bottom rakes, sides are vertical).
        """
        l_wp = self.waterplane_length(draft)
        return l_wp * self.beam**3 / 12.0

    def waterplane_inertia_longitudinal(self, draft: float) -> float:
        """Second moment of waterplane area about the transverse center (m^4).

        For longitudinal stability and trim calculations.
        I_L = (1/12) * B * L_wp^3 (approximate, treating waterplane as rectangle)

        More precisely, we need the second moment about the center of flotation.
        For a symmetric box barge (equal rakes), the center of flotation is at
        midships. For asymmetric rakes, it shifts.
        """
        # Use the full waterplane length as a first approximation
        # A more exact calculation would integrate station by station
        l_wp = self.waterplane_length(draft)
        return self.beam * l_wp**3 / 12.0

    def KB(self, draft: float) -> float:
        """Vertical position of center of buoyancy above keel (m).

        For the parallel midbody, KB = T/2.
        For rake sections, the centroid is lower because there is less
        volume near the surface. We compute by integrating.
        """
        if draft <= 0:
            return 0.0

        vol = self.displaced_volume(draft)
        if vol <= 0:
            return 0.0

        # Numerical integration: divide draft into strips
        n = 100
        dz = draft / n
        moment = 0.0
        for i in range(n):
            z = (i + 0.5) * dz  # Midpoint of strip
            # Waterplane area at this height gives the incremental volume
            # dV = A_wp(z) * dz, but we need the area of the hull cross-section at height z
            # For a box barge, at height z the cross-section width = beam everywhere
            # But the cross-section length depends on how much of the rake is submerged at height z
            a_z = self.waterplane_area(z)
            moment += z * a_z * dz

        return moment / vol

    def LCB(self, draft: float) -> float:
        """Longitudinal center of buoyancy measured from the stern (AP) (m).

        Uses the convention: x=0 at stern, x=LOA at bow.
        """
        if draft <= 0:
            return self.loa / 2.0

        vol = self.displaced_volume(draft)
        if vol <= 0:
            return self.loa / 2.0

        # Stern rake: from x=0 to x=stern_rake_length
        # Parallel midbody: from x=stern_rake_length to x=stern_rake_length + parallel_length
        # Bow rake: from x=stern_rake_length + parallel_length to x=LOA

        # Parallel midbody moment
        x_mid_start = self.stern_rake_length
        x_mid_center = x_mid_start + self.parallel_length / 2.0
        v_mid = self.beam * min(draft, self.depth) * self.parallel_length
        moment_mid = v_mid * x_mid_center

        # Stern rake moment (x measured from stern, rake extends toward bow)
        moment_stern = self._rake_first_moment_volume(
            draft, self.stern_rake_length, self.stern_rake_rise,
            x_start=0.0, toward_bow=True
        )

        # Bow rake moment (x measured from bow end of parallel body, rake extends toward bow)
        x_bow_start = self.stern_rake_length + self.parallel_length
        moment_bow = self._rake_first_moment_volume(
            draft, self.bow_rake_length, self.bow_rake_rise,
            x_start=x_bow_start, toward_bow=True
        )

        return (moment_mid + moment_stern + moment_bow) / vol

    def BM_transverse(self, draft: float) -> float:
        """Transverse metacentric radius BM = I_T / V (m)."""
        vol = self.displaced_volume(draft)
        if vol <= 0:
            return 0.0
        return self.waterplane_inertia_transverse(draft) / vol

    def BM_longitudinal(self, draft: float) -> float:
        """Longitudinal metacentric radius BM_L = I_L / V (m)."""
        vol = self.displaced_volume(draft)
        if vol <= 0:
            return 0.0
        return self.waterplane_inertia_longitudinal(draft) / vol

    # --- Surface areas for weight estimation ---

    def bottom_area(self) -> float:
        """Flat bottom plating area (m^2)."""
        return self.parallel_length * self.beam

    def side_area(self) -> float:
        """Total side plating area, both sides (m^2).

        Sides are vertical for the full LOA.
        """
        return 2.0 * self.loa * self.depth

    def deck_area(self) -> float:
        """Deck plating area (m^2).

        Deck covers the full LOA x beam.
        """
        return self.loa * self.beam

    def bow_rake_area(self) -> float:
        """Bow rake plating area (m^2).

        The rake is a sloped plate: length along slope = sqrt(rake_length^2 + rake_rise^2)
        Width = beam
        """
        if self.bow_rake_length <= 0:
            return 0.0
        slope_length = math.sqrt(self.bow_rake_length**2 + self.bow_rake_rise**2)
        return slope_length * self.beam

    def stern_rake_area(self) -> float:
        """Stern rake plating area (m^2)."""
        if self.stern_rake_length <= 0:
            return 0.0
        slope_length = math.sqrt(self.stern_rake_length**2 + self.stern_rake_rise**2)
        return slope_length * self.beam

    def total_hull_surface_area(self) -> float:
        """Total hull shell plating area (m^2)."""
        return (self.bottom_area() + self.side_area() + self.deck_area()
                + self.bow_rake_area() + self.stern_rake_area())
